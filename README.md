# Voice Scheduling Agent

A conversational, voice-enabled appointment scheduling assistant for a medical clinic. The assistant runs in your terminal, greets the patient by name, and can list doctors, check availability, book, and cancel appointments through natural conversation. Replies are also spoken aloud using text-to-speech.

## What it does

- **Conversational scheduling** — powered by Claude (Anthropic) with tool use. The model chooses when to call clinic tools like `list_doctors`, `get_available_slots`, `book_appointment`, `cancel_appointment`, and `list_my_appointments`.
- **Voice output** — every assistant reply is synthesized to speech via Speechmatics TTS and played through the system speaker (`afplay` on macOS). If TTS is not configured, the app falls back to text-only mode automatically.
- **Patient scoping** — all bookings and cancellations are tied to the patient name entered at the start of the session; the assistant refuses to act on another patient's data.
- **Audit log** — every session, user turn, tool call, tool result, and error is appended to `data/audit.jsonl` for traceability.
- **Local data** — doctors and appointments are stored as JSON files in `data/` (`doctors.json`, `appointments.json`).

## Project layout

```
main.py                          CLI entry point / conversation loop
agents/orchestrator.py           Claude client, tool schema, tool-use loop
services/doctor_service.py       List doctors, compute available slots
services/scheduling_service.py   Book / cancel / list appointments
services/tts_service.py          Speechmatics TTS + afplay playback
services/audit_service.py        JSONL audit logger
data/                            doctors.json, appointments.json, audit.jsonl
```

## Requirements

- Python 3.10+
- macOS for voice playback (uses `/usr/bin/afplay`). On other systems the app runs in text-only mode.
- An Anthropic API key
- (Optional) A Speechmatics API key for voice output

## How to run

1. Enter the project directory:

   ```bash
   cd voice-scheduling-agent
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure API keys in a `.env` file (see below).

5. Start the assistant:

   ```bash
   python main.py
   ```

   You'll be asked for your name, then you can chat with the assistant. Type `quit` or `exit` to end the call.

## API keys

Keys are loaded from a `.env` file in the project root via `python-dotenv`. **Do not hard-code keys in source and do not commit `.env` to git.**

Create a file named `.env` in the project root with the following contents:

```
ANTHROPIC_API_KEY=sk-ant-...
SPEECHMATICS_API_KEY=your-speechmatics-key
```

- `ANTHROPIC_API_KEY` — **required**. Used by [agents/orchestrator.py](agents/orchestrator.py) to call Claude. If missing or invalid, the app exits with an error.
- `SPEECHMATICS_API_KEY` — **optional**. Used by [services/tts_service.py](services/tts_service.py) for voice output. If unset, the app prints `Mode: text only` at startup and continues without speech; the conversation still works normally.

Add `.env` to your `.gitignore` so keys never get committed:

```
.env
```

Alternatively, you can export the variables in your shell instead of using a `.env` file — the code reads them from the environment either way:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export SPEECHMATICS_API_KEY=your-speechmatics-key
python main.py
```
