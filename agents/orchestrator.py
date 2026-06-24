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

SYSTEM_PROMPT = """You are a helpful scheduling assistant for a medical clinic.
You help patients book, view, and cancel appointments with doctors.

Guidelines:
- Always be polite and concise.
- When a patient asks to book an appointment, check available slots first if you don't already know them.
- Confirm booking details (doctor, date, time) with the patient before booking when the request is ambiguous.
- When listing appointments or slots, format them in a clear, readable way.
- If a patient doesn't specify a doctor but mentions a specialty, use list_doctors to find suitable doctors.
- Today's date is {today}. When patients mention relative dates like "next Monday", resolve them to YYYY-MM-DD.
- The patient's name is already known — do not ask for it."""


class LLMError(Exception):
    """Raised when the LLM call fails in an unrecoverable way."""


class Orchestrator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.history: list[dict] = []

    def run(self, patient_name: str, user_message: str) -> str:
        from datetime import date
        today = date.today().isoformat()

        self.history.append({"role": "user", "content": user_message})

        system = SYSTEM_PROMPT.format(today=today)

        while True:
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=system,
                    tools=TOOLS,
                    messages=self.history,
                    output_config={"effort": "medium"},
                )
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

            # Collect tool uses and text from this response
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if response.stop_reason == "end_turn" or not tool_uses:
                reply = " ".join(b.text for b in text_blocks).strip()
                self.history.append({"role": "assistant", "content": response.content})
                return reply

            # Append assistant turn with all content blocks
            self.history.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results
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
