# AI-Fun Architecture

## System Overview

AI-Fun is an agentic chat application that connects a local LLM (Llama 3.1) to live network infrastructure data via the Model Context Protocol (MCP). The LLM acts as an autonomous agent — it decides when to query NetBox, formulates the right API call, and summarizes the results for the user.

```
                         AI-Fun Application
 ┌─────────────────────────────────────────────────────────────────┐
 │                                                                 │
 │   ┌──────────┐       ┌───────────────┐       ┌──────────────┐  │
 │   │          │  SSE  │               │ HTTP  │              │  │
 │   │ Browser  │◄─────►│  Flask App    │◄─────►│   Ollama     │  │
 │   │   UI     │       │  (app.py)     │       │  (Llama 3.1) │  │
 │   │          │       │               │       │              │  │
 │   └──────────┘       └───────┬───────┘       └──────────────┘  │
 │                              │                                  │
 │                              │ MCP (HTTP)                       │
 │                              │                                  │
 │                      ┌───────▼───────┐                          │
 │                      │   NetBox MCP  │                          │
 │                      │    Server     │                          │
 │                      │  (port 8000)  │                          │
 │                      └───────┬───────┘                          │
 │                              │                                  │
 └──────────────────────────────┼──────────────────────────────────┘
                                │ REST API
                                │
                       ┌────────▼────────┐
                       │                 │
                       │  NetBox Cloud   │
                       │   Instance      │
                       │                 │
                       └─────────────────┘
```

## Component Details

### Browser UI (`templates/index.html`)

The frontend is a single-page chat interface that communicates with Flask via Server-Sent Events (SSE).

- Sends user messages as JSON POST to `/chat`
- Receives streamed `token` events for real-time text display
- Receives `status` events during tool execution (shows a spinner)
- Maintains conversation history client-side

### Flask App (`app.py`)

The orchestration layer that bridges the LLM, MCP, and the browser. This is where the agentic behavior lives.

**Responsibilities:**
- Serves the web UI and `/chat` SSE endpoint
- Manages the MCP client connection for tool discovery and execution
- Converts MCP tool schemas to Ollama-compatible format (with simplification)
- Fixes malformed tool arguments from the 8B model before forwarding to MCP
- Streams LLM responses token-by-token to the browser

### Ollama + Llama 3.1

The local LLM runtime. Ollama hosts the Llama 3.1 8B model and provides an HTTP API for chat completions with tool-calling support.

- Receives messages + tool definitions from Flask
- Decides autonomously whether to respond directly or invoke a tool
- Returns either text content or structured `tool_calls`

### NetBox MCP Server

An MCP-compliant server that wraps the NetBox REST API. Runs locally on port 8000 using HTTP transport.

**Exposed tools (read-only):**

| Tool | Purpose |
|------|---------|
| `netbox_get_objects` | List/filter objects by type (devices, IPs, VLANs, etc.) |
| `netbox_get_object_by_id` | Get a single object by its ID |
| `netbox_search_objects` | Global search across multiple object types |
| `netbox_get_changelogs` | View audit trail / change history |

### NetBox Cloud

The remote source of truth for network infrastructure data. The MCP server authenticates via API token and queries the REST API.

## Agentic Flow

The key architectural pattern is the **agentic tool-calling loop**. The LLM is not hard-coded to call specific tools — it autonomously decides what to do based on the user's question and the available tool definitions.

```
 User: "What devices are in my network?"
  │
  ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Step 1: Flask sends message + tool definitions to Ollama    │
 │                                                             │
 │   messages: [system_prompt, user_message]                   │
 │   tools:    [netbox_get_objects, netbox_get_object_by_id,   │
 │              netbox_search_objects, netbox_get_changelogs]   │
 └─────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Step 2: LLM decides to call a tool (autonomous decision)   │
 │                                                             │
 │   tool_calls: [{                                            │
 │     name: "netbox_get_objects",                             │
 │     arguments: {object_type: "dcim.device", filters: {}}    │
 │   }]                                                        │
 └─────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Step 3: Flask fixes arguments + executes via MCP            │
 │                                                             │
 │   fixup_tool_args() ─► MCP call_tool() ─► NetBox REST API  │
 │                                                             │
 │   Result: {"count":1, "results":[{"name":"bubba-sw1",...}]} │
 └─────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Step 4: Flask feeds tool result back to LLM                 │
 │                                                             │
 │   messages: [system, user, assistant(tool_call), tool(data)]│
 └─────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Step 5: LLM generates final response (streamed to browser)  │
 │                                                             │
 │   "There is 1 device in your network: bubba-sw1,           │
 │    a Cisco cml-iosv access switch at bubba-site1."          │
 └─────────────────────────────────────────────────────────────┘
```

For simple questions like "Hello, how are you?" the LLM skips Steps 2-4 entirely and responds directly. The decision is made by the model, not by application code.

## MCP Integration Details

### Why MCP?

The [Model Context Protocol](https://modelcontextprotocol.io/) provides a standardized way to connect LLMs to external data sources. Instead of hard-coding API calls, the app discovers tools dynamically at startup:

```
 Flask App                    MCP Server
     │                            │
     │──── initialize() ─────────►│
     │◄─── capabilities ──────────│
     │                            │
     │──── list_tools() ─────────►│
     │◄─── tool schemas ──────────│  ◄── Dynamic discovery
     │                            │
     │──── call_tool(name, args)─►│
     │◄─── result ────────────────│  ◄── Standardized execution
     │                            │
```

This means the app automatically adapts if the MCP server adds new tools — no code changes needed.

### Schema Adaptation Layer

MCP tool schemas are designed for frontier models (Claude, GPT-4) and use advanced JSON Schema features. Llama 3.1 8B requires a simpler format. The app includes an adaptation layer:

```
  MCP Tool Schema                          Ollama Tool Schema
 ┌──────────────────────┐                ┌──────────────────────┐
 │ anyOf: [             │                │                      │
 │   {type: "array"},   │  simplify()    │ type: "array"        │
 │   {type: "null"}     │ ───────────►   │ items: {type: "str"} │
 │ ]                    │                │                      │
 │ additionalProperties │                │                      │
 │ default: null        │  (stripped)    │                      │
 │ minimum: 1           │                │                      │
 │ maximum: 100         │                │                      │
 └──────────────────────┘                └──────────────────────┘

  MCP Description (6,252 chars)           Ollama Description (55 chars)
 ┌──────────────────────┐                ┌──────────────────────┐
 │ Get objects from     │  condense()    │ Get objects from     │
 │ NetBox based on...   │ ───────────►   │ NetBox based on      │
 │ [100+ object types]  │                │ their type & filters │
 │ [filter docs]        │                │                      │
 │ [pagination docs]    │                │                      │
 └──────────────────────┘                └──────────────────────┘
```

### Argument Fixup Layer

Small models frequently produce malformed tool arguments. The `fixup_tool_args()` function corrects these before forwarding to MCP:

| Model Output | Fixed Value | Issue |
|---|---|---|
| `filters: "{}"` | `filters: {}` | Dict serialized as string |
| `fields: "['id', 'name']"` | `fields: ["id", "name"]` | List as Python repr string |
| `limit: "1000"` | `limit: 100` | String instead of int + over max |
| `brief: "true"` | `brief: true` | Bool as string |
| `object_type: "device"` | `object_type: "dcim.device"` | Missing app prefix |

## Protocol & Transport Summary

| Connection | Protocol | Transport | Port |
|---|---|---|---|
| Browser to Flask | HTTP + SSE | TCP | 5001 |
| Flask to Ollama | HTTP (REST) | TCP | 11434 |
| Flask to MCP Server | MCP over HTTP | Streamable HTTP | 8000 |
| MCP Server to NetBox | HTTPS (REST) | TCP | 443 |
