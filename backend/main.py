from __future__ import annotations

import csv
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "businesses.csv"
DB_FILE = ROOT / "appointments.db"
FRONTEND = ROOT / "frontend"
SLOTS = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]


def load_businesses() -> list[dict[str, Any]]:
    with DATA_FILE.open(newline="", encoding="utf-8") as file:
        return [
            {**row, "services": row["services"].split("|")}
            for row in csv.DictReader(file)
        ]


BUSINESSES = load_businesses()
BUSINESS_BY_ID = {business["business_id"]: business for business in BUSINESSES}


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS appointments (
                appointment_id TEXT PRIMARY KEY, business_id TEXT NOT NULL,
                customer_name TEXT NOT NULL, customer_phone TEXT DEFAULT '',
                service TEXT NOT NULL, appointment_date TEXT NOT NULL,
                appointment_time TEXT NOT NULL, duration INTEGER DEFAULT 30,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        count = db.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
        if count == 0:
            now = datetime.now().isoformat(timespec="seconds")
            for index in range(16):
                business = BUSINESSES[index % len(BUSINESSES)]
                slot = SLOTS[(index * 2) % len(SLOTS)]
                day = (date.today() + timedelta(days=index % 4)).isoformat()
                db.execute(
                    "INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"APT-{10001 + index}", business["business_id"], ["Rahul", "Priya", "Aman", "Neha"][index % 4],
                     "", business["services"][0], day, slot, 30, "BOOKED", now, now),
                )


class AppointmentRequest(BaseModel):
    business_id: str
    customer_name: str = Field(min_length=1, max_length=80)
    customer_phone: str = Field(default="", max_length=30)
    service: str
    appointment_date: str
    appointment_time: str


class AgentRequest(BaseModel):
    business_id: str
    message: str = Field(min_length=1, max_length=500)
    session_id: str = "demo"


def appointment_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def resolve_date(text: str) -> str | None:
    today = date.today()
    lowered = text.lower()
    if "today" in lowered:
        return today.isoformat()
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()
    weekdays = {name.lower(): number for number, name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}
    for name, target in weekdays.items():
        if name in lowered:
            delta = (target - today.weekday()) % 7 or 7
            return (today + timedelta(days=delta)).isoformat()
    match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lowered)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            return None
    return None


def resolve_time(text: str) -> str | None:
    match = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", text.lower())
    if not match:
        match = re.search(r"\b([01]\d|2[0-3]):([0-5]\d)\b", text)
        return f"{match.group(1)}:{match.group(2)}" if match else None
    hour, minutes, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minutes:02d}"


def detect_intent(message: str) -> str:
    text = message.lower()
    if any(word in text for word in ["cancel", "delete", "remove"]):
        return "CANCEL"
    if any(word in text for word in ["reschedule", "move", "change my"]):
        return "RESCHEDULE"
    if any(word in text for word in ["available", "availability", "open slots", "what times"]):
        return "CHECK_AVAILABILITY"
    if any(word in text for word in ["book", "schedule", "appointment", "reserve"]):
        return "BOOK"
    if any(word in text for word in ["hi", "hello", "hey"]):
        return "GREETING"
    if any(word in text for word in ["yes", "confirm", "okay", "sure"]):
        return "CONFIRM"
    return "HELP"


def find_service(message: str, business: dict[str, Any]) -> str | None:
    lowered = message.lower()
    for service in business["services"]:
        if service.lower() in lowered or any(word in lowered for word in service.lower().split() if len(word) > 4):
            return service
    return None


def is_available(business_id: str, appointment_date: str, appointment_time: str, ignore_id: str | None = None) -> bool:
    with connection() as db:
        row = db.execute(
            "SELECT 1 FROM appointments WHERE business_id=? AND appointment_date=? AND appointment_time=? AND status='BOOKED' AND appointment_id != ?",
            (business_id, appointment_date, appointment_time, ignore_id or ""),
        ).fetchone()
    return row is None and appointment_time in SLOTS


app = FastAPI(title="Aditya AI Voice Enterprise", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_db()


@app.get("/api/businesses")
def businesses(category: str | None = None, city: str | None = None):
    rows = BUSINESSES
    if category:
        rows = [item for item in rows if item["category"] == category]
    if city:
        rows = [item for item in rows if item["city"].lower() == city.lower()]
    return rows


@app.get("/api/businesses/{business_id}")
def business(business_id: str):
    if business_id not in BUSINESS_BY_ID:
        raise HTTPException(404, "Business not found")
    return BUSINESS_BY_ID[business_id]


@app.get("/api/availability")
def availability(business_id: str, appointment_date: str = Query(...)):
    if business_id not in BUSINESS_BY_ID:
        raise HTTPException(404, "Business not found")
    with connection() as db:
        booked = {row["appointment_time"] for row in db.execute(
            "SELECT appointment_time FROM appointments WHERE business_id=? AND appointment_date=? AND status='BOOKED'",
            (business_id, appointment_date),
        )}
    return [{"time": slot, "available": slot not in booked} for slot in SLOTS]


@app.get("/api/appointments")
def appointments(business_id: str | None = None):
    query = "SELECT * FROM appointments"
    params: tuple[str, ...] = ()
    if business_id:
        query += " WHERE business_id=?"
        params = (business_id,)
    query += " ORDER BY appointment_date, appointment_time"
    with connection() as db:
        return [appointment_dict(row) for row in db.execute(query, params)]


@app.post("/api/appointments", status_code=201)
def create_appointment(request: AppointmentRequest):
    business = BUSINESS_BY_ID.get(request.business_id)
    if not business:
        raise HTTPException(404, "Business not found")
    if request.service not in business["services"]:
        raise HTTPException(400, "Service is not offered by this business")
    try:
        date.fromisoformat(request.appointment_date)
    except ValueError as error:
        raise HTTPException(400, "Invalid appointment date") from error
    if not is_available(request.business_id, request.appointment_date, request.appointment_time):
        raise HTTPException(409, "That time is not available")
    now = datetime.now().isoformat(timespec="seconds")
    record = (f"APT-{uuid.uuid4().hex[:8].upper()}", request.business_id, request.customer_name.strip(),
              request.customer_phone, request.service, request.appointment_date, request.appointment_time, 30, "BOOKED", now, now)
    with connection() as db:
        db.execute("INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", record)
    return dict(zip(
        ["appointment_id", "business_id", "customer_name", "customer_phone", "service",
         "appointment_date", "appointment_time", "duration", "status", "created_at", "updated_at"],
        record,
    ))


@app.patch("/api/appointments/{appointment_id}")
def update_appointment(appointment_id: str, request: AppointmentRequest):
    if not is_available(request.business_id, request.appointment_date, request.appointment_time, appointment_id):
        raise HTTPException(409, "That time is not available")
    now = datetime.now().isoformat(timespec="seconds")
    with connection() as db:
        cursor = db.execute(
            "UPDATE appointments SET business_id=?, customer_name=?, customer_phone=?, service=?, appointment_date=?, appointment_time=?, status='BOOKED', updated_at=? WHERE appointment_id=?",
            (request.business_id, request.customer_name, request.customer_phone, request.service, request.appointment_date, request.appointment_time, now, appointment_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Appointment not found")
        row = db.execute("SELECT * FROM appointments WHERE appointment_id=?", (appointment_id,)).fetchone()
    return appointment_dict(row)


@app.delete("/api/appointments/{appointment_id}")
def cancel_appointment(appointment_id: str):
    with connection() as db:
        cursor = db.execute("UPDATE appointments SET status='CANCELLED', updated_at=? WHERE appointment_id=?", (datetime.now().isoformat(timespec="seconds"), appointment_id))
        if cursor.rowcount == 0:
            raise HTTPException(404, "Appointment not found")
    return {"status": "CANCELLED", "appointment_id": appointment_id}


@app.post("/api/agent/message")
def agent_message(request: AgentRequest):
    business = BUSINESS_BY_ID.get(request.business_id)
    if not business:
        raise HTTPException(404, "Business not found")
    intent = detect_intent(request.message)
    appointment_date, appointment_time, service = resolve_date(request.message), resolve_time(request.message), find_service(request.message, business)
    if intent == "GREETING":
        response = f"Hello! I’m ready to help with {business['business_name']}. You can book, reschedule, cancel, or check availability."
    elif intent == "CHECK_AVAILABILITY":
        day = appointment_date or date.today().isoformat()
        with connection() as db:
            booked = {row["appointment_time"] for row in db.execute("SELECT appointment_time FROM appointments WHERE business_id=? AND appointment_date=? AND status='BOOKED'", (request.business_id, day))}
        open_slots = [slot for slot in SLOTS if slot not in booked]
        response = f"I found {len(open_slots)} available slots for {day}: {', '.join(open_slots[:6])}."
    elif intent == "BOOK":
        missing = "date" if not appointment_date else "time" if not appointment_time else "service" if not service else None
        if missing:
            response = {"date": "What date would you prefer?", "time": "What time would you prefer?", "service": f"Which service would you like? We offer {', '.join(business['services'])}."}[missing]
        elif not is_available(request.business_id, appointment_date, appointment_time):
            response, appointment_time = f"The {appointment_time} slot is already booked. Please choose another time.", None
        else:
            response = f"I found an available {service} appointment on {appointment_date} at {appointment_time}. Would you like me to book it?"
    elif intent == "CANCEL":
        response = "Please provide your appointment ID so I can cancel it safely."
    elif intent == "RESCHEDULE":
        response = "Please provide your appointment ID, new date, and new time to reschedule."
    elif intent == "CONFIRM":
        response = "Please use the Confirm button on the appointment card after reviewing the details."
    else:
        response = "I can book, reschedule, cancel, or find availability. Try: “Book a dental cleaning tomorrow at 4 PM.”"
    return {"intent": intent, "response": response, "entities": {"date": appointment_date, "time": appointment_time, "service": service}, "requires_confirmation": intent == "BOOK" and bool(appointment_date and appointment_time and service)}


@app.get("/")
def landing():
    return FileResponse(FRONTEND / "index.html")


app.mount("/app", StaticFiles(directory=FRONTEND, html=True), name="frontend")
