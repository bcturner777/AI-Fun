#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Check required env vars
if [ -z "$NETBOX_URL" ] || [ -z "$NETBOX_TOKEN" ]; then
    echo "Error: NETBOX_URL and NETBOX_TOKEN must be set in .env or environment"
    exit 1
fi

MCP_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."
    if [ -n "$MCP_PID" ] && kill -0 "$MCP_PID" 2>/dev/null; then
        kill "$MCP_PID"
        wait "$MCP_PID" 2>/dev/null
    fi
    exit 0
}

trap cleanup INT TERM

# Start NetBox MCP server in background (HTTP transport on port 8000)
echo "Starting NetBox MCP server on http://127.0.0.1:8000/mcp ..."
TRANSPORT=http HOST=127.0.0.1 PORT=8000 \
    uv --directory "$SCRIPT_DIR/netbox-mcp-server" run netbox-mcp-server &
MCP_PID=$!

# Wait for MCP server to accept TCP connections
echo "Waiting for MCP server..."
MCP_READY=false
for i in $(seq 1 30); do
    if ! kill -0 "$MCP_PID" 2>/dev/null; then
        echo "Error: MCP server process exited."
        exit 1
    fi
    # Check if port 8000 is accepting connections (works regardless of HTTP method)
    if nc -z 127.0.0.1 8000 2>/dev/null; then
        echo "MCP server is ready."
        MCP_READY=true
        break
    fi
    sleep 1
done

if [ "$MCP_READY" = false ]; then
    echo "Warning: MCP server did not become ready in 30s, starting Flask anyway."
fi

# Start Flask app
echo "Starting Flask app on http://localhost:5001 ..."
"$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/app.py"
