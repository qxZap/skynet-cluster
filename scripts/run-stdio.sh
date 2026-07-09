#!/usr/bin/env bash
# Run the cluster MCP server over stdio (for clients that don't speak HTTP/SSE,
# e.g. `claude mcp add ... -- scripts/run-stdio.sh`).
#
# Talks to the already-running HTTP cluster (scripts/run-cluster.ps1 / the
# LaunchAgent) over loopback — set SELF_URL if it's not on the default port.
#
#   ./scripts/run-stdio.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

"$PYTHON" -m pip install -q -r "$ROOT/cluster/requirements.txt"

export SELF_URL="${SELF_URL:-http://127.0.0.1:18888}"

exec "$PYTHON" -m cluster.stdio_server
