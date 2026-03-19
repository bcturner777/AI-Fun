import ollama
import sys


def chat():
    model = "mistral"
    history = []

    print(f"Chat with {model} (type 'quit' to exit)")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        history.append({"role": "user", "content": user_input})

        try:
            response = ollama.chat(
                model=model,
                messages=history,
                stream=True,
            )

            print(f"\n{model}: ", end="", flush=True)
            full_response = ""
            for chunk in response:
                token = chunk["message"]["content"]
                print(token, end="", flush=True)
                full_response += token
            print()

            history.append({"role": "assistant", "content": full_response})

        except ollama.ResponseError as e:
            print(f"\nError: {e}")
            history.pop()  # remove the failed user message


if __name__ == "__main__":
    chat()
