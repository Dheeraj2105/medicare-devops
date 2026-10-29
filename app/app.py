"""MediCare+ - Hospital management service (patients, doctors, appointments)."""
import os
import re
import socket
import sqlite3
from datetime import date, datetime, timezone

from flask import Flask, g, jsonify, render_template, request

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_COLOR = os.getenv("APP_COLOR", "blue")
DB_PATH = os.getenv("DB_PATH", "/tmp/medicare.db")

GENDERS = {"Male", "Female", "Other"}
BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
STATUSES = {"scheduled", "completed", "cancelled"}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,79}$")
PHONE_RE = re.compile(r"^\d{10}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    specialty TEXT NOT NULL,
    room TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    gender TEXT NOT NULL,
    blood_group TEXT NOT NULL,
    phone TEXT NOT NULL,
    diagnosis TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled'
);
"""

SEED_DOCTORS = [
    ("Dr. Ananya Rao", "Cardiology", "C-101"),
    ("Dr. Vikram Mehta", "Neurology", "N-204"),
    ("Dr. Priya Nair", "Pediatrics", "P-008"),
    ("Dr. Arjun Iyer", "Orthopedics", "O-112"),
    ("Dr. Kavya Reddy", "Dermatology", "D-019"),
    ("Dr. Rahul Sharma", "General Medicine", "G-001"),
]

APPT_BY_ID = """
SELECT a.id, a.date, a.time, a.reason, a.status, a.patient_id, a.doctor_id,
       p.name AS patient, d.name AS doctor, d.specialty
FROM appointments a
JOIN patients p ON p.id = a.patient_id
JOIN doctors d ON d.id = a.doctor_id
WHERE a.id = ?
"""
APPT_ALL = """
SELECT a.id, a.date, a.time, a.reason, a.status, a.patient_id, a.doctor_id,
       p.name AS patient, d.name AS doctor, d.specialty
FROM appointments a
JOIN patients p ON p.id = a.patient_id
JOIN doctors d ON d.id = a.doctor_id
ORDER BY a.date, a.time
"""
APPT_BY_STATUS = """
SELECT a.id, a.date, a.time, a.reason, a.status, a.patient_id, a.doctor_id,
       p.name AS patient, d.name AS doctor, d.specialty
FROM appointments a
JOIN patients p ON p.id = a.patient_id
JOIN doctors d ON d.id = a.doctor_id
WHERE a.status = ?
ORDER BY a.date, a.time
"""

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    try:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT OR IGNORE INTO doctors (name, specialty, room) VALUES (?, ?, ?)",
            SEED_DOCTORS,
        )
        con.commit()
    finally:
        con.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def error(messages, status=400):
    if isinstance(messages, str):
        messages = [messages]
    return jsonify({"errors": messages}), status


def mask_phone(phone):
    if len(phone) <= 4:
        return "****"
    return "*" * (len(phone) - 4) + phone[-4:]


def patient_dict(row):
    data = dict(row)
    data["phone"] = mask_phone(data["phone"])
    return data


def count(sql, params=()):
    return get_db().execute(sql, params).fetchone()[0]


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return error("Not found", 404)
    return "Not found", 404


@app.errorhandler(413)
def too_large(_e):
    return error("Payload too large", 413)


@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION, color=APP_COLOR)


@app.get("/health")
def health():
    get_db().execute("SELECT 1")
    return jsonify({"status": "UP", "version": APP_VERSION, "color": APP_COLOR})


@app.get("/api/info")
def info():
    return jsonify({
        "app": "MediCare+",
        "version": APP_VERSION,
        "color": APP_COLOR,
        "pod": socket.gethostname(),
    })


@app.get("/api/stats")
def stats():
    today = date.today().isoformat()
    return jsonify({
        "patients": count("SELECT COUNT(*) FROM patients"),
        "doctors": count("SELECT COUNT(*) FROM doctors"),
        "appointments": count("SELECT COUNT(*) FROM appointments"),
        "today": count(
            "SELECT COUNT(*) FROM appointments WHERE date = ? AND status = 'scheduled'",
            (today,),
        ),
        "scheduled": count("SELECT COUNT(*) FROM appointments WHERE status = 'scheduled'"),
        "completed": count("SELECT COUNT(*) FROM appointments WHERE status = 'completed'"),
    })


def validate_patient(data):
    errs = []
    name = str(data.get("name", "")).strip()
    if not NAME_RE.match(name):
        errs.append("Name must be 2-80 letters")
    raw_age = data.get("age")
    age = None
    try:
        if isinstance(raw_age, bool):
            raise ValueError
        age = int(raw_age)
        if not 0 <= age <= 130:
            raise ValueError
    except (TypeError, ValueError):
        errs.append("Age must be between 0 and 130")
    gender = str(data.get("gender", ""))
    if gender not in GENDERS:
        errs.append("Gender must be Male, Female or Other")
    blood_group = str(data.get("blood_group", ""))
    if blood_group not in BLOOD_GROUPS:
        errs.append("Invalid blood group")
    phone = str(data.get("phone", "")).strip()
    if not PHONE_RE.match(phone):
        errs.append("Phone must be exactly 10 digits")
    diagnosis = str(data.get("diagnosis", "") or "").strip()
    if len(diagnosis) > 200:
        errs.append("Diagnosis must be under 200 characters")
    clean = {
        "name": name, "age": age, "gender": gender,
        "blood_group": blood_group, "phone": phone, "diagnosis": diagnosis,
    }
    return clean, errs


@app.get("/api/patients")
def list_patients():
    q = request.args.get("q", "").strip()[:80]
    db = get_db()
    if q:
        like = f"%{q}%"
        rows = db.execute(
            "SELECT * FROM patients WHERE name LIKE ? OR diagnosis LIKE ? ORDER BY id DESC",
            (like, like),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM patients ORDER BY id DESC").fetchall()
    return jsonify([patient_dict(r) for r in rows])


@app.post("/api/patients")
def create_patient():
    clean, errs = validate_patient(json_body())
    if errs:
        return error(errs)
    db = get_db()
    cur = db.execute(
        "INSERT INTO patients (name, age, gender, blood_group, phone, diagnosis, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (clean["name"], clean["age"], clean["gender"], clean["blood_group"],
         clean["phone"], clean["diagnosis"],
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.commit()
    row = db.execute("SELECT * FROM patients WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(patient_dict(row)), 201


@app.delete("/api/patients/<int:pid>")
def delete_patient(pid):
    db = get_db()
    cur = db.execute("DELETE FROM patients WHERE id = ?", (pid,))
    db.commit()
    if cur.rowcount == 0:
        return error("Patient not found", 404)
    return jsonify({"deleted": pid})


@app.get("/api/doctors")
def list_doctors():
    rows = get_db().execute(
        "SELECT d.*, (SELECT COUNT(*) FROM appointments a "
        "WHERE a.doctor_id = d.id AND a.status = 'scheduled') AS upcoming "
        "FROM doctors d ORDER BY d.name"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/appointments")
def list_appointments():
    status = request.args.get("status", "")
    db = get_db()
    if status in STATUSES:
        rows = db.execute(APPT_BY_STATUS, (status,)).fetchall()
    else:
        rows = db.execute(APPT_ALL).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/appointments")
def create_appointment():
    data = json_body()
    errs = []
    patient_id = doctor_id = None
    try:
        patient_id = int(data.get("patient_id"))
    except (TypeError, ValueError):
        errs.append("Select a valid patient")
    try:
        doctor_id = int(data.get("doctor_id"))
    except (TypeError, ValueError):
        errs.append("Select a valid doctor")
    appt_date = str(data.get("date", ""))
    try:
        date.fromisoformat(appt_date)
    except ValueError:
        errs.append("Date must be YYYY-MM-DD")
    appt_time = str(data.get("time", ""))
    try:
        datetime.strptime(appt_time, "%H:%M")
    except ValueError:
        errs.append("Time must be HH:MM")
    reason = str(data.get("reason", "") or "").strip()
    if len(reason) > 200:
        errs.append("Reason must be under 200 characters")
    if errs:
        return error(errs)
    db = get_db()
    if not db.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone():
        return error("Patient not found", 404)
    if not db.execute("SELECT 1 FROM doctors WHERE id = ?", (doctor_id,)).fetchone():
        return error("Doctor not found", 404)
    cur = db.execute(
        "INSERT INTO appointments (patient_id, doctor_id, date, time, reason) VALUES (?, ?, ?, ?, ?)",
        (patient_id, doctor_id, appt_date, appt_time, reason),
    )
    db.commit()
    row = db.execute(APPT_BY_ID, (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.patch("/api/appointments/<int:aid>")
def update_appointment(aid):
    status = str(json_body().get("status", ""))
    if status not in STATUSES:
        return error("Status must be scheduled, completed or cancelled")
    db = get_db()
    cur = db.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, aid))
    db.commit()
    if cur.rowcount == 0:
        return error("Appointment not found", 404)
    return jsonify({"id": aid, "status": status})


init_db()
