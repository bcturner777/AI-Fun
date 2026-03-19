import asyncio
import json
import os

import ollama
from dotenv import load_dotenv
from flask import Flask, Response, render_template, request
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

app = Flask(__name__)

MODEL = "llama3.1"
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")

SYSTEM_PROMPT = (
    "You are a helpful network assistant. You have tools that query a live NetBox system. "
    "When the user asks about network infrastructure, call the appropriate tool, wait for "
    "the result, and then present the returned data in a clear summary. "
    "Never explain how to use the API. Never write code. Never make up data. "
    "object_type must use dotted format like 'dcim.device', 'ipam.ipaddress', 'dcim.site'. "
    "filters must be a JSON object like {} or {\"status\": \"active\"}."
)

# Global store for MCP tools in Ollama format
ollama_tools = []
mcp_tool_names = {}
tools_discovered = False


def ensure_tools():
    """Discover MCP tools if not already done. Safe to call repeatedly."""
    global ollama_tools, mcp_tool_names, tools_discovered
    if tools_discovered:
        return
    try:
        ollama_tools, mcp_tool_names = asyncio.run(discover_tools())
        tools_discovered = True
        print(f"Discovered {len(ollama_tools)} MCP tools: {list(mcp_tool_names.keys())}")
    except Exception as e:
        print(f"Warning: Could not connect to MCP server: {e}")


ALLOWED_SCHEMA_KEYS = {"type", "description", "properties", "required", "items", "enum"}


def simplify_schema(schema):
    """Simplify a JSON Schema for Ollama compatibility.

    Ollama's tool parser chokes on anyOf, additionalProperties, default,
    minimum/maximum, and other advanced JSON Schema features. Keep only
    the core keys that Ollama understands.
    """
    if not isinstance(schema, dict):
        return schema

    result = {}

    # Resolve anyOf: pick the first non-null type
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            if option.get("type") != "null":
                result.update(simplify_schema(option))
                break
        if "description" in schema:
            result["description"] = schema["description"]
        return result

    for key, value in schema.items():
        if key not in ALLOWED_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            result[key] = {k: simplify_schema(v) for k, v in value.items()}
        elif key == "items" and isinstance(value, dict):
            result[key] = simplify_schema(value)
        else:
            result[key] = value

    return result


def condense_description(description):
    """Condense a tool description to its first paragraph.

    Llama 3.1 8B's tool-calling breaks when descriptions are too long
    (thousands of chars with embedded docs). Keep just the summary.
    """
    if not description:
        return ""
    return description.strip().split("\n\n")[0].strip()


async def discover_tools():
    """Connect to MCP server and discover available tools."""
    async with streamable_http_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = []
            names = {}
            for tool in result.tools:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": condense_description(tool.description),
                        "parameters": simplify_schema(tool.inputSchema),
                    },
                })
                names[tool.name] = tool.description or tool.name
            return tools, names


def fixup_tool_args(name, args):
    """Fix common argument mistakes from small models.

    Llama 3.1 8B frequently serializes dicts/lists as strings, passes
    wrong types for ints/bools, omits dotted prefixes on object_type,
    and exceeds limits. Coerce everything before sending to MCP.
    """
    args = dict(args)

    # --- Type coercion ---

    # Dicts passed as JSON strings
    for key in ("filters",):
        if key in args and isinstance(args[key], str):
            try:
                args[key] = json.loads(args[key])
            except (json.JSONDecodeError, TypeError):
                args[key] = {}

    # Lists passed as strings (JSON or Python repr)
    for key in ("fields", "object_types", "ordering"):
        val = args.get(key)
        if isinstance(val, str):
            # Try JSON first, then Python-style single quotes
            for attempt in (val, val.replace("'", '"')):
                try:
                    parsed = json.loads(attempt)
                    if isinstance(parsed, list):
                        args[key] = parsed
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

    # Ints passed as strings
    for key in ("limit", "offset", "object_id"):
        if key in args and isinstance(args[key], str):
            try:
                args[key] = int(args[key])
            except ValueError:
                pass

    # Bools passed as strings
    for key in ("brief",):
        val = args.get(key)
        if isinstance(val, str):
            args[key] = val.lower() in ("true", "1", "yes")

    # Clamp limit to 1–100
    if "limit" in args and isinstance(args["limit"], int):
        args["limit"] = max(1, min(args["limit"], 100))

    # --- Semantic fixes ---

    # Fix object_type missing app prefix (e.g. "device" → "dcim.device")
    ot = args.get("object_type", "")
    if ot and "." not in ot:
        prefix_map = {
            "device": "dcim.device", "site": "dcim.site", "rack": "dcim.rack",
            "interface": "dcim.interface", "cable": "dcim.cable",
            "manufacturer": "dcim.manufacturer", "platform": "dcim.platform",
            "ipaddress": "ipam.ipaddress", "prefix": "ipam.prefix",
            "vlan": "ipam.vlan", "vrf": "ipam.vrf",
            "virtualmachine": "virtualization.virtualmachine",
            "cluster": "virtualization.cluster",
            "circuit": "circuits.circuit", "provider": "circuits.provider",
            "tenant": "tenancy.tenant",
        }
        args["object_type"] = prefix_map.get(ot.lower(), f"dcim.{ot.lower()}")

    # Strip None-valued keys (model sometimes sends ordering=None)
    args = {k: v for k, v in args.items() if v is not None}

    return args


async def execute_tool(name, arguments):
    """Execute a tool via MCP and return the text result."""
    arguments = fixup_tool_args(name, arguments)
    async with streamable_http_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            texts = []
            for content in result.content:
                if hasattr(content, "text"):
                    texts.append(content.text)
            return "\n".join(texts) if texts else str(result)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    # Lazy tool discovery — retry if startup failed
    ensure_tools()

    data = request.get_json()
    user_message = data.get("message", "")
    history = data.get("history", [])

    history.append({"role": "user", "content": user_message})

    # Prepend system prompt for Ollama calls
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    def generate():
        try:
            # Stream first response (may include tool calls)
            stream = ollama.chat(
                model=MODEL,
                messages=messages,
                tools=ollama_tools or None,
                stream=True,
            )

            full_content = ""
            tool_calls = []

            for chunk in stream:
                msg = chunk["message"]
                if msg.get("content"):
                    token = msg["content"]
                    full_content += token
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])

            if tool_calls:
                # Add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": tool_calls,
                })

                for tc in tool_calls:
                    fn = tc["function"]
                    tool_name = fn["name"]
                    tool_args = fn.get("arguments", {})

                    yield f"data: {json.dumps({'type': 'status', 'content': f'Calling {tool_name}...'})}\n\n"

                    try:
                        result = asyncio.run(execute_tool(tool_name, tool_args))
                    except Exception as e:
                        result = f"Tool error: {e}"

                    messages.append({"role": "tool", "content": result})

                # Second call with tool results — stream final answer
                stream2 = ollama.chat(model=MODEL, messages=messages, stream=True)
                for chunk in stream2:
                    token = chunk["message"].get("content", "")
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            yield "data: [DONE]\n\n"
        except ollama.ResponseError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# Try to discover tools at startup (will retry on first request if this fails)
ensure_tools()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
