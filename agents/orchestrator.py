import json
import os
from dotenv import load_dotenv
import anthropic
from anthropic import APIConnectionError, APIStatusError, APITimeoutError

from services.doctor_service import list_doctors, get_available_slots
from services.scheduling_service import book_appointment, cancel_appointment, list_appointments

load_dotenv()

TOOLS = [
    {
        "name": "list_doctors",
        "description": "List all doctors at the clinic with their id, name, and specialty.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_available_slots",
        "description": (
            "Get available 30-minute appointment slots for a specific doctor on a given date. "
            "Use this before booking to confirm a slot exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string", "description": "The doctor's id (e.g. 'd1')"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["doctor_id", "date"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment for the current patient with a doctor at a specific date and time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string", "description": "The doctor's id"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Time slot in HH:MM format (e.g. '09:30')"},
            },
            "required": ["doctor_id", "date", "time"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel one of the current patient's booked appointments by its id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string", "description": "The appointment id to cancel"},
            },
            "required": ["appointment_id"],
        },
    },
    {
        "name": "list_my_appointments",
        "description": "List all upcoming booked appointments for the current patient.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

SYSTEM_PROMPT = """You are a warm, professional scheduling assistant for a medical clinic.
The patient you are speaking with is {patient_name}. Today's date is {today}.

Available specialties at this clinic:
- General Practice
- Cardiology
- Dermatology
- Pediatrics
- Orthopedics

Tone and manner:
- Speak in a calm, reassuring, and human tone. Patients may be calling about health concerns — acknowledge that and make them feel cared for.
- Be professional yet warm. Avoid cold or robotic phrasing.
- Assure the patient that the clinic provides the best possible care and that you are here to help them every step of the way.
- Keep responses concise and easy to follow.

Conversation flow:
- At the very start of each call, greet {patient_name} warmly by name and introduce yourself as the clinic's appointment assistant.
- When the patient signals they are done (says goodbye, thank you, etc.), close the conversation gracefully: thank them for calling, wish them good health, and say goodbye.

Scheduling guidelines:
- All operations are for {patient_name} only. If the patient asks to view, book, or cancel appointments for a different person, politely but firmly decline. Explain that for privacy and security, each patient can only manage their own appointments, and advise them that the other person should call in separately. Do not proceed with the request.
- When a patient asks to book an appointment, check available slots first if you don't already know them.
- Confirm booking details (doctor, date, time) with the patient before booking when the request is ambiguous.
- If a patient doesn't specify a doctor but mentions a specialty, use list_doctors to find suitable doctors.
- When presenting available slots, suggest only the 3 most suitable times (prefer earlier slots in the day). Do not list every slot.
- When checking doctors for a given date, only mention doctors who have available slots on that date — skip any doctor whose get_available_slots result shows available: false.
- Never suggest or book appointments in the past. All suggested dates and times must be from now onward.
- Always display times to the patient in 12-hour format with AM/PM (e.g. "9:00 AM", "2:30 PM"). Time values sent to tools must remain in 24-hour HH:MM format.
- If a patient requests a specialty not listed above, inform them it is not available at this clinic and recommend General Practice as an alternative."""


class LLMError(Exception):
    """Raised when the LLM call fails in an unrecoverable way."""


class Orchestrator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.history: list[dict] = []

    def _system(self, patient_name: str) -> str:
        from datetime import date
        return SYSTEM_PROMPT.format(patient_name=patient_name, today=date.today().isoformat())

    def _call(self, system: str, use_tools: bool = True) -> object:
        try:
            kwargs = dict(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system,
                messages=self.history,
                output_config={"effort": "medium"},
            )
            if use_tools:
                kwargs["tools"] = TOOLS
            return self.client.messages.create(**kwargs)
        except APIConnectionError:
            raise LLMError("Could not reach the Anthropic API. Check your internet connection.")
        except APITimeoutError:
            raise LLMError("The request to the Anthropic API timed out. Please try again later.")
        except APIStatusError as e:
            if e.status_code == 401:
                raise LLMError("Invalid API key. Please check your ANTHROPIC_API_KEY in .env.")
            if e.status_code == 429:
                raise LLMError("Rate limit exceeded. Please wait a moment and try again.")
            raise LLMError(f"Anthropic API error ({e.status_code}): {e.message}")

    def greet(self, patient_name: str) -> str:
        """Generate the opening greeting for the patient."""
        system = self._system(patient_name)
        trigger = {"role": "user", "content": "[Patient has connected to the appointment line.]"}
        self.history.append(trigger)
        response = self._call(system, use_tools=False)
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        self.history.append({"role": "assistant", "content": response.content})
        return text

    def run(self, patient_name: str, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        system = self._system(patient_name)

        while True:
            response = self._call(system)

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if response.stop_reason == "end_turn" or not tool_uses:
                reply = " ".join(b.text for b in text_blocks).strip()
                self.history.append({"role": "assistant", "content": response.content})
                return reply

            self.history.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_use in tool_uses:
                result = self._dispatch(patient_name, tool_use.name, tool_use.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                })

            self.history.append({"role": "user", "content": tool_results})

    def _dispatch(self, patient_name: str, tool_name: str, inputs: dict):
        if tool_name == "list_doctors":
            return list_doctors()
        if tool_name == "get_available_slots":
            return get_available_slots(inputs["doctor_id"], inputs["date"])
        if tool_name == "book_appointment":
            return book_appointment(patient_name, inputs["doctor_id"], inputs["date"], inputs["time"])
        if tool_name == "cancel_appointment":
            return cancel_appointment(patient_name, inputs["appointment_id"])
        if tool_name == "list_my_appointments":
            return list_appointments(patient_name)
        return {"error": f"Unknown tool: {tool_name}"}
