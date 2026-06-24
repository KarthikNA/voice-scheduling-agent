import sys
from agents.orchestrator import Orchestrator, LLMError

FAREWELL = (
    "\nThank you for calling our clinic. "
    "We wish you good health and a wonderful day ahead. "
    "Take care, and goodbye!"
)


def main():
    print("=" * 52)
    print("   Clinic Appointment Scheduling Assistant")
    print("=" * 52)
    print("Type 'quit' or 'exit' to end the call.\n")

    patient_name = input("Please enter your name: ").strip()
    if not patient_name:
        print("Name cannot be empty. Exiting.")
        sys.exit(1)

    orchestrator = Orchestrator()

    try:
        greeting = orchestrator.greet(patient_name)
    except LLMError as e:
        print(f"\nError: {e}")
        print("Unable to connect. Please try again later.")
        sys.exit(1)

    print(f"\nAssistant: {greeting}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(FAREWELL)
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit"}:
            print(FAREWELL)
            break

        try:
            reply = orchestrator.run(patient_name, user_input)
        except LLMError as e:
            print(f"\nError: {e}")
            print("The session has ended due to an unrecoverable error. Goodbye!")
            sys.exit(1)

        print(f"\nAssistant: {reply}\n")


if __name__ == "__main__":
    main()
