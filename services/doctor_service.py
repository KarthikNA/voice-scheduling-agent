import json
from datetime import date as date_type, datetime
from pathlib import Path
import calendar

DOCTORS_FILE = Path(__file__).parent.parent / "data" / "doctors.json"
APPOINTMENTS_FILE = Path(__file__).parent.parent / "data" / "appointments.json"


def _load_doctors() -> list[dict]:
    with open(DOCTORS_FILE) as f:
        return json.load(f)


def _load_appointments() -> list[dict]:
    with open(APPOINTMENTS_FILE) as f:
        return json.load(f)


def list_doctors() -> list[dict]:
    """Return all doctors with id, name, and specialty."""
    return [
        {"id": d["id"], "name": d["name"], "specialty": d["specialty"]}
        for d in _load_doctors()
    ]


def get_available_slots(doctor_id: str, date: str) -> dict:
    """
    Return available time slots for a doctor on a given date (YYYY-MM-DD).
    Returns a dict with 'available' bool, 'slots' list, and context fields.
    Past dates and past time slots (for today) are excluded.
    """
    doctors = {d["id"]: d for d in _load_doctors()}
    doctor = doctors.get(doctor_id)
    if not doctor:
        return {"available": False, "reason": "doctor_not_found", "slots": []}

    today = date_type.today()
    parsed = date_type.fromisoformat(date)

    if parsed < today:
        return {
            "available": False,
            "reason": "past_date",
            "doctor_name": doctor["name"],
            "slots": [],
            "message": "Cannot book appointments for a date in the past.",
        }

    day_name = calendar.day_name[parsed.weekday()]
    all_slots = doctor["availability"].get(day_name, [])

    if not all_slots:
        return {
            "available": False,
            "reason": "not_working",
            "doctor_name": doctor["name"],
            "day": day_name,
            "slots": [],
            "message": f"{doctor['name']} does not work on {day_name}s.",
        }

    booked = {
        a["time"]
        for a in _load_appointments()
        if a["doctor_id"] == doctor_id
        and a["date"] == date
        and a["status"] == "booked"
    }

    free_slots = [s for s in all_slots if s not in booked]

    # Filter out past time slots when the date is today
    if parsed == today:
        now = datetime.now().time()
        free_slots = [
            s for s in free_slots
            if datetime.strptime(s, "%H:%M").time() > now
        ]

    if not free_slots:
        return {
            "available": False,
            "reason": "fully_booked",
            "doctor_name": doctor["name"],
            "day": day_name,
            "slots": [],
            "message": f"{doctor['name']} has no remaining available slots on {date} ({day_name}).",
        }

    return {
        "available": True,
        "doctor_name": doctor["name"],
        "specialty": doctor["specialty"],
        "day": day_name,
        "date": date,
        "slots": free_slots,
    }


def get_doctor(doctor_id: str) -> dict | None:
    """Return a single doctor record by id."""
    doctors = {d["id"]: d for d in _load_doctors()}
    return doctors.get(doctor_id)
