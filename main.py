import sys
from agents.orchestrator import Orchestrator, LLMError
from services.audit_service import AuditLogger
from services.tts_service import speak, is_configured as tts_configured, check as tts_check

FAREWELL = (
    "Thank you for calling our clinic. "
    "We wish you good health and a wonderful day ahead. "
    "Take care, and goodbye!"
)


def main():
    print("=" * 52)
    print("   Clinic Appointment Scheduling Assistant")
    print("=" * 52)
    tts_problems = tts_check()
    if tts_problems:
        print("Mode: text only")
        for problem in tts_problems:
            print(f"  [TTS] {problem}")
    else:
        print("Mode: voice + text")
    print("Type 'quit' or 'exit' to end the call.\n")

    patient_name = input("Please enter your name: ").strip()
    if not patient_name:
        print("Name cannot be empty. Exiting.")
        sys.exit(1)

    audit = AuditLogger(patient_name)
    audit.session_start()

    orchestrator = Orchestrator(audit=audit)

    greeting = orchestrator.greet(patient_name)
    print(f"\nAssistant: {greeting}\n")
    speak(greeting)

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            audit.session_end(reason="keyboard_interrupt")
            print(f"\nAssistant: {FAREWELL}")
            speak(FAREWELL)
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit"}:
            audit.session_end(reason="user_quit")
            print(f"\nAssistant: {FAREWELL}")
            speak(FAREWELL)
            break

        audit.user_message(user_input)

        try:
            reply = orchestrator.run(patient_name, user_input)
        except LLMError as e:
            audit.error(str(e), fatal=True, context="main_loop")
            print(f"\nError: {e}")
            print("The session has ended. Goodbye!")
            audit.session_end(reason="fatal_error")
            sys.exit(1)

        audit.assistant_reply(reply)
        print(f"\nAssistant: {reply}\n")
        speak(reply)


if __name__ == "__main__":
    main()
