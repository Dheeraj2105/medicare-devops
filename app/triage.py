"""MediCare+ Smart Triage - explainable rule-based patient risk scoring."""
from flask import Blueprint, jsonify, render_template

LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
LEVEL_CLASS = {
    "CRITICAL": "pill",
    "HIGH": "status status-scheduled",
    "MEDIUM": "status status-cancelled",
    "LOW": "status status-completed",
}
RULES = [
    (("chest pain", "heart attack", "cardiac", "stroke", "seizure",
      "unconscious", "bleeding", "breathless", "difficulty breathing"), 50, "Emergency symptom"),
    (("fracture", "high fever", "infection", "asthma", "diabetes",
              "hypertension", "pneumonia", "covid", "cancer", "tumor"), 25, "Serious condition"),
    (("fever", "cough", "pain", "injury", "vomiting", "headache"), 10, "Common symptom"),
]
RARE_BLOOD = ("A-", "B-", "AB-", "O-")


def score_patient(patient):
    """Return an explainable risk score (0-100), level and reasons."""
    score = 0
    reasons = []
    age = int(patient["age"])
    if age >= 75:
        score += 25
        reasons.append("Age 75+")
    elif age >= 60:
        score += 15
        reasons.append("Age 60+")
    elif age <= 5:
        score += 15
        reasons.append("Child under 5")
    text = (patient.get("diagnosis") or "").lower()
    for keywords, points, label in RULES:
        hit = next((k for k in keywords if k in text), None)
        if hit:
            score += points
            reasons.append(f"{label}: {hit}")
            break
    if patient.get("blood_group") in RARE_BLOOD:
        score += 5
        reasons.append(f"Rare blood group {patient['blood_group']}")
    score = min(score, 100)
    if score >= 60:
        level = "CRITICAL"
    elif score >= 35:
        level = "HIGH"
    elif score >= 15:
        level = "MEDIUM"
    else:
        level = "LOW"
    if not reasons:
        reasons.append("No risk factors")
    return {"score": score, "level": level, "reasons": reasons}


def create_triage_blueprint(get_db, patient_dict, version, color):
    bp = Blueprint("triage", __name__)

    def build_queue():
        rows = get_db().execute("SELECT * FROM patients").fetchall()
        queue = []
        for row in rows:
            p = patient_dict(row)
            p.update(score_patient(p))
            p["css"] = LEVEL_CLASS[p["level"]]
            queue.append(p)
        queue.sort(key=lambda x: (-x["score"], x["id"]))
        return queue

    @bp.get("/api/triage")
    def triage_api():
        return jsonify(build_queue())

    @bp.get("/triage")
    def triage_page():
        queue = build_queue()
        counts = {lvl: sum(1 for q in queue if q["level"] == lvl) for lvl in LEVELS}
        return render_template("triage.html", queue=queue, counts=counts,
                               levels=LEVELS, version=version, color=color)

    return bp
