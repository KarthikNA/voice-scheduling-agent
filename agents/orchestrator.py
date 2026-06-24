import json
import os
from dotenv import load_dotenv
import anthropic
from anthropic import APIConnectionError, APIStatusError, APITimeoutError

from services.doctor_service import list_doctors, get_available_slots
from services.scheduling_service import book_appointment, cancel_appointment, list_appointments
from services.audit_service import AuditLogger

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

Speech output format — CRITICAL:
- Your responses are read aloud to the patient. Write exactly as you would speak.
- Do NOT use any markdown: no asterisks, no bullet points, no dashes, no numbered lists, no headers, no bold or italic.
- Do NOT use abbreviations or symbols that sound unnatural when read aloud (e.g. write "9 in the morning" not "9:00 AM" when in a sentence; for standalone times write "9:00 AM" naturally).
- Keep responses short and conversational — one or two sentences for confirmations, a short natural paragraph at most for more complex answers.
- When listing options, weave them into natural speech: "We have slots at 9 AM, 10:30 AM, and 2 PM" rather than a list.

Conversation flow:
- At the very start of each call, greet {patient_name} warmly by name and introduce yourself as the clinic appointment assistant.
- When the patient signals they are done, close gracefully: thank them for calling and wish them good health.

Scheduling guidelines:
- All operations are for {patient_name} only. If the patient asks to view, book, or cancel appointments for a different person, politely but firmly decline. Explain that for privacy and security each patient can only manage their own appointments, and advise the other person to call in separately.
- When a patient asks to book an appointment, check available slots first if you don't already know them.
- Confirm booking details with the patient before booking when the request is ambiguous.
- If a patient doesn't specify a doctor but mentions a specialty, use list_doctors to find suitable doctors.
- When presenting available slots, suggest only the 3 most suitable times in natural speech. Do not list every slot.
- When checking doctors for a given date, only mention doctors who have available slots on that date — skip any whose get_available_slots result shows available: false.
- Never suggest or book appointments in the past.
- Time values sent to tools must be in 24-hour HH:MM format.
- After a booking or cancellation succeeds, confirm it in one or two natural sentences and stop — do not make additional tool calls to re-verify.
- If a patient requests a specialty not listed above, inform them it is not available and recommend General Practice.
- If a patient asks anything about medications, dosages, side effects, drug interactions, prescriptions, or any other medical or clinical advice, do not answer. Politely explain that you are only able to help with appointment scheduling, and assure them that their doctor will be the best person to advise them on that during their appointment."""

MAX_TOOL_ROUNDS = 8

_FALLBACK_GREETING = (
    "Hello {patient_name}, welcome to our clinic's appointment service. "
    "I'm here to help you book, view, or cancel appointments. How can I assist you today?"
)
_TRANSIENT_ERROR_MSG = (
    "I'm sorry, I'm having a bit of trouble right now. "
    "Could you please repeat that, or give me just a moment?"
)


class LLMError(Exception):
    """Raised when the LLM call fails."""
    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


class Orchestrator:
    def __init__(self, audit: AuditLogger):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.history: list[dict] = []
        self.audit = audit

    def _system(self, patient_name: str) -> str:
        from datetime import date
        return SYSTEM_PROMPT.format(patient_name=patient_name, today=date.today().isoformat())

    def _call(self, system: str, use_tools: bool = True) -> object:
        try:
            kwargs = dict(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=system,
                messages=self.history,
                output_config={"effort": "medium"},
            )
            if use_tools:
                kwargs["tools"] = TOOLS
            return self.client.messages.create(**kwargs)
        except APIConnectionError as e:
            raise LLMError(f"Network error reaching the API: {e}", fatal=False)
        except APITimeoutError:
            raise LLMError("The API request timed out.", fatal=False)
        except APIStatusError as e:
            if e.status_code == 401:
                raise LLMError(
                    "Invalid API key. Please check ANTHROPIC_API_KEY in .env.", fatal=True
                )
            if e.status_code == 429:
                raise LLMError("Rate limit hit. Please wait a moment.", fatal=False)
            if e.status_code >= 500:
                raise LLMError(f"Anthropic server error ({e.status_code}).", fatal=False)
            raise LLMError(
                f"Anthropic API error ({e.status_code}): {e.message}", fatal=True
            )

    def greet(self, patient_name: str) -> str:
        """
        Generate the opening greeting for the patient.
        Falls back to a hardcoded message if the API is unreachable so the session can still start.
        """
        system = self._system(patient_name)
        trigger = {"role": "user", "content": "[Patient has connected to the appointment line.]"}
        self.history.append(trigger)
        try:
            response = self._call(system, use_tools=False)
            text = " ".join(b.text for b in response.content if b.type == "text").strip()
            if not text:
                raise ValueError("Empty greeting response")
            self.history.append({"role": "assistant", "content": response.content})
        except Exception as e:
            self.audit.error(str(e), fatal=False, context="greet")
            text = _FALLBACK_GREETING.format(patient_name=patient_name)
            self.history.append({"role": "assistant", "content": text})
        self.audit.greeting(text)
        return text

    def run(self, patient_name: str, user_message: str) -> str:
        """
        Process one patient message and return the assistant reply.
        Raises LLMError(fatal=True) for unrecoverable failures (bad key, etc.).
        Returns a polite in-conversation message for transient failures so the
        caller can keep the session alive.
        """
        self.history.append({"role": "user", "content": user_message})
        system = self._system(patient_name)

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = self._call(system)
            except LLMError as e:
                self.audit.error(str(e), fatal=e.fatal, context="llm_call")
                if e.fatal:
                    raise
                self.history.pop()
                return _TRANSIENT_ERROR_MSG

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if response.stop_reason in ("end_turn", "max_tokens") or not tool_uses:
                reply = " ".join(b.text for b in text_blocks).strip()
                if not reply:
                    reply = "I'm sorry, I didn't get a response. Could you please try again?"
                self.history.append({"role": "assistant", "content": response.content})
                return reply

            self.history.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_use in tool_uses:
                self.audit.tool_call(tool_use.name, tool_use.input)
                result = self._dispatch(patient_name, tool_use.name, tool_use.input)
                self.audit.tool_result(tool_use.name, result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                })

            self.history.append({"role": "user", "content": tool_results})

        self.audit.error("Max tool rounds exceeded", fatal=False, context="run_loop")
        return "I'm sorry, I seem to be going in circles. Could you rephrase your request?"

    def _dispatch(self, patient_name: str, tool_name: str, inputs: dict) -> dict:
        """Call the appropriate service function and return a result or error dict."""
        try:
            if tool_name == "list_doctors":
                return list_doctors()
            if tool_name == "get_available_slots":
                return get_available_slots(inputs["doctor_id"], inputs["date"])
            if tool_name == "book_appointment":
                return book_appointment(
                    patient_name, inputs["doctor_id"], inputs["date"], inputs["time"]
                )
            if tool_name == "cancel_appointment":
                return cancel_appointment(patient_name, inputs["appointment_id"])
            if tool_name == "list_my_appointments":
                return list_appointments(patient_name)
            return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"error": f"An internal error occurred while running '{tool_name}': {e}"}

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
