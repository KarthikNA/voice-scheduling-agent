import sys
from agents.orchestrator import Orchestrator


def main():
    print("=" * 50)
    print("  Clinic Appointment Scheduling Assistant")
    print("=" * 50)
    print("Type 'quit' or 'exit' to leave.\n")

    patient_name = input("Please enter your name: ").strip()
    if not patient_name:
        print("Name cannot be empty. Exiting.")
        sys.exit(1)

    print(f"\nHello, {patient_name}! How can I help you today?\n")

    orchestrator = Orchestrator()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit"}:
            print("Goodbye!")
            break

        reply = orchestrator.run(patient_name, user_input)
        print(f"\nAssistant: {reply}\n")


if __name__ == "__main__":
    main()
