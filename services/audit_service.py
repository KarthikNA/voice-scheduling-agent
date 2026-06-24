import json
import uuid
from datetime import datetime
from pathlib import Path

AUDIT_FILE = Path(__file__).parent.parent / "data" / "audit.jsonl"


class AuditLogger:
    def __init__(self, patient_name: str):
        self.session_id = str(uuid.uuid4())
        self.patient_name = patient_name
        # Ensure the data directory exists so the first write never fails
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: str, data: dict | None = None) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "patient_name": self.patient_name,
            "event": event,
            "data": data or {},
        }
        # "a" = append — existing entries are never overwritten across restarts
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def session_start(self) -> None:
        self._write("session_start")

    def session_end(self, reason: str = "user_quit") -> None:
        self._write("session_end", {"reason": reason})

    def user_message(self, message: str) -> None:
        self._write("user_message", {"message": message})

    def greeting(self, text: str) -> None:
        self._write("greeting", {"text": text})

    def assistant_reply(self, text: str) -> None:
        self._write("assistant_reply", {"text": text})

    def tool_call(self, tool_name: str, inputs: dict) -> None:
        self._write("tool_call", {"tool": tool_name, "inputs": inputs})

    def tool_result(self, tool_name: str, result: object) -> None:
        self._write("tool_result", {"tool": tool_name, "result": result})

    def error(self, message: str, fatal: bool = False, context: str = "") -> None:
        self._write("error", {"message": message, "fatal": fatal, "context": context})
