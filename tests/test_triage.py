from app import app as flask_app
from triage import score_patient


def test_elderly_chest_pain_is_critical():
    r = score_patient({"age": 80, "diagnosis": "Chest pain", "blood_group": "O+"})
    assert r["score"] == 75
    assert r["level"] == "CRITICAL"


def test_healthy_adult_is_low():
    r = score_patient({"age": 30, "diagnosis": "", "blood_group": "B+"})
    assert r["score"] == 0
    assert r["level"] == "LOW"


def test_triage_queue_sorted_and_explained():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        c.post("/api/patients", json={"name": "Low Risk", "age": 25, "gender": "Male",
                                      "blood_group": "O+", "phone": "9000000001", "diagnosis": ""})
        c.post("/api/patients", json={"name": "High Risk", "age": 78, "gender": "Female",
                                      "blood_group": "AB-", "phone": "9000000002", "diagnosis": "Stroke"})
        queue = c.get("/api/triage").get_json()
        assert queue[0]["score"] >= queue[-1]["score"]
        assert queue[0]["reasons"]
        assert queue[0]["phone"].startswith("*")
        assert c.get("/triage").status_code == 200
