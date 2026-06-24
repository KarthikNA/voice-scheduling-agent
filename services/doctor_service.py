import json
from pathlib import Path

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


def get_available_slots(doctor_id: str, date: str) -> list[str]:
    """
    Return free time slots for a doctor on a given date (YYYY-MM-DD).
    Slots already booked are excluded.
    """
    from datetime import date as date_type
    import calendar

    doctors = {d["id"]: d for d in _load_doctors()}
    doctor = doctors.get(doctor_id)
    if not doctor:
        return []

    parsed = date_type.fromisoformat(date)
    day_name = calendar.day_name[parsed.weekday()]  # e.g. "Monday"

    all_slots = doctor["availability"].get(day_name, [])
    if not all_slots:
        return []

    booked = {
        a["time"]
        for a in _load_appointments()
        if a["doctor_id"] == doctor_id
        and a["date"] == date
        and a["status"] == "booked"
    }

    return [s for s in all_slots if s not in booked]


def get_doctor(doctor_id: str) -> dict | None:
    """Return a single doctor record by id."""
    doctors = {d["id"]: d for d in _load_doctors()}
    return doctors.get(doctor_id)
