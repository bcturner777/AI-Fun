import json
import ollama
from flask import Flask, Response, render_template, request

app = Flask(__name__)

MODEL = "mistral"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    history = data.get("history", [])

    history.append({"role": "user", "content": user_message})

    def generate():
        try:
            stream = ollama.chat(model=MODEL, messages=history, stream=True)
            for chunk in stream:
                token = chunk["message"]["content"]
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except ollama.ResponseError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
