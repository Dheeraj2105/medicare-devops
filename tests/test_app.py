import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def new_patient(client, **overrides):
    payload = {
        "name": "Ravi Kumar", "age": 45, "gender": "Male",
        "blood_group": "B+", "phone": "9876543210", "diagnosis": "Hypertension",
    }
    payload.update(overrides)
    return client.post("/api/patients", json=payload)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "UP"


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"MediCare" in r.data


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_doctors_seeded(client):
    assert len(client.get("/api/doctors").get_json()) >= 6


def test_create_patient_masks_phone(client):
    r = new_patient(client)
    assert r.status_code == 201
    assert r.get_json()["phone"] == "******3210"


def test_rejects_invalid_patient(client):
    r = new_patient(client, age=500, phone="12ab")
    assert r.status_code == 400
    assert len(r.get_json()["errors"]) == 2


def test_sql_injection_is_harmless(client):
    new_patient(client, name="Meena Das")
    r = client.get("/api/patients", query_string={"q": "' OR 1=1 --"})
    assert r.status_code == 200
    assert r.get_json() == []


def test_appointment_lifecycle(client):
    pid = new_patient(client, name="Sita Devi").get_json()["id"]
    did = client.get("/api/doctors").get_json()[0]["id"]
    r = client.post("/api/appointments", json={
        "patient_id": pid, "doctor_id": did,
        "date": "2030-01-15", "time": "10:30", "reason": "Routine checkup",
    })
    assert r.status_code == 201
    aid = r.get_json()["id"]
    r = client.patch(f"/api/appointments/{aid}", json={"status": "completed"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "completed"


def test_delete_patient(client):
    pid = new_patient(client, name="Temp Patient").get_json()["id"]
    assert client.delete(f"/api/patients/{pid}").status_code == 200
    assert client.delete(f"/api/patients/{pid}").status_code == 404


def test_unknown_api_returns_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert "errors" in r.get_json()
