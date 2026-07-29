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

## Architecture

The system is a small, layered CLI application. Each layer has a single responsibility, and data flows in one direction: the CLI drives the orchestrator, which drives the LLM and dispatches its tool calls to the service layer, which reads and writes local JSON files.

```
     ┌──────────────────────────────────────────────┐
     │  main.py  (CLI loop, TTS playback, exit)     │
     └───────────────┬──────────────────────────────┘
                     │ user turn / assistant reply
                     ▼
     ┌──────────────────────────────────────────────┐
     │  agents/orchestrator.py                      │
     │  - Anthropic client (Claude Sonnet)          │
     │  - System prompt + tool schema               │
     │  - Tool-use loop (up to 8 rounds)            │
     │  - Error taxonomy (LLMError, fatal vs not)   │
     └───┬───────────────────────────┬──────────────┘
         │ tool_use                  │ every event
         ▼                           ▼
  ┌──────────────────┐      ┌────────────────────────┐
  │  services/       │      │  services/             │
  │  doctor_service  │      │  audit_service         │
  │  scheduling_svc  │      │  (append to JSONL)     │
  └────────┬─────────┘      └───────────┬────────────┘
           │                            │
           ▼                            ▼
   data/doctors.json              data/audit.jsonl
   data/appointments.json
```

### Components

- **CLI layer — [main.py](main.py)**
  Prompts for the patient's name, runs the input/output loop, calls `Orchestrator.greet` once and `Orchestrator.run` per turn, prints assistant replies, and hands each reply to the TTS service. It also handles graceful exits (`quit`, `exit`, Ctrl-C) and terminates the process on fatal `LLMError`.

- **Agent layer — [agents/orchestrator.py](agents/orchestrator.py)**
  Owns the Anthropic client, the conversation history, the system prompt (rendered with the patient name and today's date), and the tool schema. On each turn it runs a bounded loop: call Claude → if the response contains `tool_use` blocks, execute them via `_dispatch` and feed the `tool_result` blocks back → repeat until Claude returns plain text (`end_turn`) or the round budget is exhausted. All API errors are normalized into `LLMError(fatal=…)` so the CLI can decide whether to keep the session alive or exit.

- **Service layer — [services/](services)**
  Pure Python functions that implement the tools exposed to the model:
  - `doctor_service.list_doctors`, `get_available_slots` — read `data/doctors.json`, cross-reference `data/appointments.json`, and filter out past dates, past times on today, and slots the doctor doesn't work.
  - `scheduling_service.book_appointment`, `cancel_appointment`, `list_appointments` — read/write `data/appointments.json`. Every mutation is scoped to the current `patient_name`, which is passed in by the orchestrator (never by the model), so a patient cannot act on someone else's data even if the LLM is coaxed to try.
  - `tts_service.speak` — asynchronously calls Speechmatics TTS, writes the WAV to a temp file, and plays it via `afplay`. `check()` runs a pre-flight (API key present, SDK importable, `afplay` available) so the CLI can announce text-only mode cleanly. TTS failures are logged to stderr but never break the session.
  - `audit_service.AuditLogger` — appends one JSON object per event (`session_start`, `user_message`, `tool_call`, `tool_result`, `assistant_reply`, `error`, `session_end`) to `data/audit.jsonl`, giving a full replay of every session.

- **Data layer — [data/](data)**
  Flat JSON files. `doctors.json` is seed data (id, name, specialty, weekly availability). `appointments.json` is the mutable booking store. `audit.jsonl` is append-only.

### Key design choices

- **Tools instead of prompt-only scheduling.** The model never invents slots or appointment ids; it must go through the tool schema, and each tool returns structured JSON the model narrates back in natural speech.
- **Patient identity is server-side.** The orchestrator injects `patient_name` into every mutating tool call; the model has no way to override it.
- **Fail soft on transient errors, hard on config errors.** Network blips or 429s return a polite retry message and pop the last user turn from history; a bad API key raises `LLMError(fatal=True)` and ends the session.
- **Voice is optional and isolated.** The TTS service can be missing keys, missing SDK, or fail at runtime — none of it affects the conversation.

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
