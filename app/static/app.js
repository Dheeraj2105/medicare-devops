"use strict";

const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  let data = null;
  try { data = await res.json(); } catch (_) { data = null; }
  if (!res.ok) {
    throw new Error(data && data.errors ? data.errors.join(" | ") : res.statusText);
  }
  return data;
}

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}

function row(cells) {
  const tr = document.createElement("tr");
  cells.forEach((c) => {
    const td = document.createElement("td");
    if (c instanceof Node) td.appendChild(c);
    else td.textContent = c === undefined || c === null ? "" : String(c);
    tr.appendChild(td);
  });
  return tr;
}

function emptyRow(tbody, cols, text) {
  const tr = document.createElement("tr");
  const td = el("td", text, "empty");
  td.colSpan = cols;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

function flash(target, text, ok) {
  target.textContent = text;
  target.className = "msg " + (ok ? "ok" : "err");
  setTimeout(() => { target.textContent = ""; target.className = "msg"; }, 4000);
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function statusBadge(status) {
  return el("span", status, "status status-" + status);
}

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
}

async function loadInfo() {
  const info = await api("/api/info");
  $("#podName").textContent = info.pod;
}

async function loadStats() {
  const s = await api("/api/stats");
  $("#statPatients").textContent = s.patients;
  $("#statDoctors").textContent = s.doctors;
  $("#statToday").textContent = s.today;
  $("#statScheduled").textContent = s.scheduled;
  $("#statCompleted").textContent = s.completed;
}

async function loadPatients() {
  const q = $("#patientSearch").value.trim();
  const list = await api("/api/patients" + (q ? "?q=" + encodeURIComponent(q) : ""));
  const body = $("#patientBody");
  body.replaceChildren();
  if (!list.length) { emptyRow(body, 8, "No patients found"); return; }
  list.forEach((p) => {
    const del = el("button", "Remove", "btn-sm danger");
    del.addEventListener("click", async () => {
      if (!confirm("Remove " + p.name + " and all their appointments?")) return;
      try { await api("/api/patients/" + p.id, { method: "DELETE" }); refreshAll(); }
      catch (err) { alert(err.message); }
    });
    body.appendChild(row(["#" + p.id, p.name, p.age, p.gender, el("span", p.blood_group, "pill"),
      p.phone, p.diagnosis || "-", del]));
  });
}

async function loadPatientOptions() {
  const list = await api("/api/patients");
  const sel = $("#apptPatient");
  sel.replaceChildren();
  if (!list.length) {
    const o = el("option", "Register a patient first");
    o.value = "";
    sel.appendChild(o);
    return;
  }
  list.forEach((p) => {
    const o = el("option", "#" + p.id + " - " + p.name);
    o.value = p.id;
    sel.appendChild(o);
  });
}

async function loadDoctors() {
  const list = await api("/api/doctors");
  const grid = $("#doctorGrid");
  const sel = $("#apptDoctor");
  grid.replaceChildren();
  sel.replaceChildren();
  list.forEach((d) => {
    const card = el("div", null, "doctor");
    card.append(
      el("div", d.name.replace("Dr. ", "").charAt(0), "avatar"),
      el("h3", d.name),
      el("p", d.specialty, "muted"),
      el("p", "Room " + d.room + " | " + d.upcoming + " upcoming", "small")
    );
    grid.appendChild(card);
    const o = el("option", d.name + " - " + d.specialty);
    o.value = d.id;
    sel.appendChild(o);
  });
}

function actionBtn(label, cls, id, status) {
  const b = el("button", label, "btn-sm " + cls);
  b.addEventListener("click", async () => {
    try {
      await api("/api/appointments/" + id, { method: "PATCH", body: JSON.stringify({ status }) });
      refreshAll();
    } catch (err) { alert(err.message); }
  });
  return b;
}

async function loadAppointments() {
  const filter = $("#apptFilter").value;
  const list = await api("/api/appointments" + (filter ? "?status=" + filter : ""));
  const body = $("#apptBody");
  body.replaceChildren();
  if (!list.length) { emptyRow(body, 7, "No appointments"); return; }
  list.forEach((a) => {
    const actions = el("div");
    if (a.status === "scheduled") {
      actions.append(actionBtn("Complete", "ok", a.id, "completed"), actionBtn("Cancel", "danger", a.id, "cancelled"));
    }
    body.appendChild(row([a.date, a.time, a.patient, a.doctor + " (" + a.specialty + ")",
      a.reason || "-", statusBadge(a.status), actions]));
  });
}

async function loadUpcoming() {
  const list = await api("/api/appointments?status=scheduled");
  const body = $("#upcomingBody");
  body.replaceChildren();
  if (!list.length) { emptyRow(body, 4, "No upcoming appointments"); return; }
  list.slice(0, 6).forEach((a) => {
    body.appendChild(row([a.date + " " + a.time, a.patient, a.doctor, statusBadge(a.status)]));
  });
}

function refreshAll() {
  return Promise.all([
    loadStats(), loadPatients(), loadPatientOptions(), loadDoctors(), loadAppointments(), loadUpcoming(),
  ]).catch((err) => console.error(err));
}

$("#patientForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  data.age = Number(data.age);
  try {
    const p = await api("/api/patients", { method: "POST", body: JSON.stringify(data) });
    flash($("#patientMsg"), "Registered " + p.name + " (#" + p.id + ")", true);
    form.reset();
    refreshAll();
  } catch (err) { flash($("#patientMsg"), err.message, false); }
});

$("#apptForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  data.patient_id = Number(data.patient_id);
  data.doctor_id = Number(data.doctor_id);
  try {
    const a = await api("/api/appointments", { method: "POST", body: JSON.stringify(data) });
    flash($("#apptMsg"), "Booked " + a.patient + " with " + a.doctor, true);
    refreshAll();
  } catch (err) { flash($("#apptMsg"), err.message, false); }
});

document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));
$("#patientSearch").addEventListener("input", debounce(() => loadPatients().catch(console.error), 250));
$("#apptFilter").addEventListener("change", () => loadAppointments().catch(console.error));
$("#apptDate").value = new Date().toISOString().slice(0, 10);

loadInfo().catch(console.error);
refreshAll();
