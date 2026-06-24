import json
import uuid
from pathlib import Path

from services.doctor_service import get_available_slots, get_doctor

APPOINTMENTS_FILE = Path(__file__).parent.parent / "data" / "appointments.json"


def _load() -> list[dict]:
    with open(APPOINTMENTS_FILE) as f:
        return json.load(f)


def _save(appointments: list[dict]) -> None:
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(appointments, f, indent=2)


def book_appointment(patient_name: str, doctor_id: str, date: str, time: str) -> dict:
    """
    Book a slot for a patient. Returns the new appointment or an error dict.
    date: YYYY-MM-DD, time: HH:MM (24-hour)
    """
    doctor = get_doctor(doctor_id)
    if not doctor:
        return {"error": f"No doctor found with id '{doctor_id}'."}

    slots_info = get_available_slots(doctor_id, date)
    if not slots_info["available"]:
        return {"error": slots_info.get("message", "No slots available.")}

    if time not in slots_info["slots"]:
        return {
            "error": f"{time} is not available for {doctor['name']} on {date}. "
                     f"Available slots: {', '.join(slots_info['slots'])}."
        }

    appointments = _load()

    # Block patient from booking any doctor at a timeslot they already have covered
    for a in appointments:
        if (
            a["patient_name"].lower() == patient_name.lower()
            and a["date"] == date
            and a["time"] == time
            and a["status"] == "booked"
        ):
            return {
                "error": f"You already have an appointment at {time} on {date} "
                         f"with {a['doctor_name']}. You cannot book two appointments at the same time."
            }

    appointment = {
        "id": str(uuid.uuid4())[:8],
        "patient_name": patient_name,
        "doctor_id": doctor_id,
        "doctor_name": doctor["name"],
        "specialty": doctor["specialty"],
        "date": date,
        "time": time,
        "status": "booked",
    }
    appointments.append(appointment)
    _save(appointments)
    return appointment


def cancel_appointment(patient_name: str, appointment_id: str) -> dict:
    """
    Cancel an appointment. Only the patient who booked it can cancel it.
    Returns the cancelled appointment or an error dict.
    """
    appointments = _load()
    for a in appointments:
        if a["id"] == appointment_id:
            if a["patient_name"].lower() != patient_name.lower():
                return {"error": "You can only cancel your own appointments."}
            if a["status"] == "cancelled":
                return {"error": "This appointment is already cancelled."}
            a["status"] = "cancelled"
            _save(appointments)
            return a
    return {"error": f"No appointment found with id '{appointment_id}'."}


def list_appointments(patient_name: str) -> list[dict]:
    """Return all booked appointments for a patient."""
    return [
        a for a in _load()
        if a["patient_name"].lower() == patient_name.lower()
        and a["status"] == "booked"
    ]
