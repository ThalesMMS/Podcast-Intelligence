#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
MCP_URL="${MCP_URL:-http://localhost:8001/mcp}"

if command -v python3 >/dev/null 2>&1; then
  JSON_PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  JSON_PYTHON="python"
else
  echo "smoke_test.sh requires python3 or python to format JSON responses." >&2
  exit 127
fi

curl --fail --silent "${API_URL}/health/live" | "${JSON_PYTHON}" -m json.tool
curl --fail --silent "${API_URL}/health/ready" | "${JSON_PYTHON}" -m json.tool
curl --fail --silent "${API_URL}/v1/providers" | "${JSON_PYTHON}" -m json.tool

echo "REST smoke checks passed. MCP endpoint configured at ${MCP_URL}."
