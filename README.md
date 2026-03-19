# AI-Fun

A local AI chat app powered by [Ollama](https://ollama.com/) and the Mistral model. Includes both a command-line interface and a browser-based web UI with real-time streaming responses.

## Prerequisites

- **Python 3.9+**
- **[Ollama](https://ollama.com/)** installed and running locally
- **Mistral model** pulled in Ollama:
  ```bash
  ollama pull mistral
  ```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install ollama flask
```

## Usage

### CLI Chat

```bash
python chat.py
```

An interactive terminal chat. Type your messages and get streaming responses. Type `quit` or `exit` to end the session.

### Web UI

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser. Features:

- Chat interface with message bubbles
- Real-time token-by-token streaming via Server-Sent Events
- Conversation history maintained across messages
- "New Chat" button to start a fresh conversation

## Project Structure

```
chat.py              # CLI chat interface
app.py               # Flask web server with SSE streaming
templates/index.html # Browser-based chat UI
```
