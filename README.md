# AI-Fun

A local AI chat app powered by [Ollama](https://ollama.com/) and Llama 3.1, with [NetBox](https://netboxlabs.com/) integration via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). Ask questions about your network infrastructure directly in the chat and get live answers from your NetBox inventory.

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** installed and running locally
- **Llama 3.1 model** pulled in Ollama:
  ```bash
  ollama pull llama3.1
  ```
- **[uv](https://docs.astral.sh/uv/)** (for the MCP server):
  ```bash
  brew install uv
  ```
- **A NetBox instance** with an API token

## Setup

```bash
# Clone the NetBox MCP server
git clone https://github.com/netboxlabs/netbox-mcp-server.git
cd netbox-mcp-server && uv sync && cd ..

# Create Python venv and install dependencies
python3.10 -m venv venv
source venv/bin/activate
pip install flask ollama python-dotenv "mcp[cli]"
```

### Environment Variables

Create a `.env` file in the project root:

```
NETBOX_URL=https://your-instance.cloud.netboxapp.com
NETBOX_TOKEN=your_api_token_here
```

| Variable | Description | Default |
|----------|-------------|---------|
| `NETBOX_URL` | Your NetBox instance URL | *(required)* |
| `NETBOX_TOKEN` | NetBox API token (read-only is fine) | *(required)* |
| `MCP_URL` | MCP server endpoint | `http://127.0.0.1:8000/mcp` |

## Usage

### Quick Start

```bash
./start.sh
```

This starts both the NetBox MCP server (port 8000) and the Flask chat app (port 5001). Open [http://localhost:5001](http://localhost:5001) in your browser.

### Manual Start

```bash
# Terminal 1: Start the MCP server
source .env
TRANSPORT=http uv --directory netbox-mcp-server run netbox-mcp-server

# Terminal 2: Start the Flask app
source venv/bin/activate
python app.py
```

### CLI Chat

```bash
python chat.py
```

An interactive terminal chat (no MCP/tool support).

## Features

- Chat with Llama 3.1 via a browser-based UI with real-time streaming (SSE)
- Query NetBox infrastructure data through natural language (devices, IPs, sites, VLANs, etc.)
- MCP tool integration with automatic tool discovery from the NetBox MCP server
- Visual status indicators in the UI while tools execute ("Calling netbox_get_objects...")
- Argument fixup layer that coerces the 8B model's common mistakes (type mismatches, missing prefixes, limit clamping)
- Simplified tool schemas and condensed descriptions for reliable tool calling with smaller models
- Conversation history and "New Chat" to start fresh

## How It Works

1. On startup, the app connects to the NetBox MCP server and discovers available tools (`netbox_get_objects`, `netbox_get_object_by_id`, `netbox_search_objects`, `netbox_get_changelogs`)
2. Tool schemas are simplified and descriptions condensed for Llama 3.1 8B compatibility
3. When you ask a question, Ollama decides whether to call a tool or respond directly
4. If a tool is called, the app executes it via MCP, feeds the result back, and streams the final summary

## Project Structure

```
app.py               # Flask web server with MCP tool integration
templates/index.html # Browser-based chat UI
start.sh             # Starts MCP server + Flask app
chat.py              # CLI chat interface (no tool support)
.env                 # NetBox credentials (gitignored)
netbox-mcp-server/   # Cloned NetBox MCP server (gitignored)
```
