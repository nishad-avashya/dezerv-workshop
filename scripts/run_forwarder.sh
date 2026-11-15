#!/usr/bin/env bash
# run_forwarder.sh [NAME] [PORT]: start the Go alert forwarder (Lab B Part 2) in THIS terminal. Run from anywhere.
#   NAME  factory agent (reads agents/NAME/.state.json); empty = Lab A's agent (.labA.json)
#   PORT  listen port, default 8090 (8080 is taken by the workshop editor)
# Handles: Go not on PATH (adds ~/.local/go/bin), relative paths (always runs from the repo root), a busy port, no Go at all
# (falls back to bin/alert-forwarder from `make go-prebuilt`). It stays in the foreground; send the alert from a second terminal.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
NAME="$(echo "${1:-}" | tr -d "[:space:]")"; PORT="$(echo "${2:-8090}" | tr -d "[:space:]")"; PORT="${PORT:-8090}"
case "$PORT" in (*[!0-9]*) echo "ERROR: PORT must be a number, got '$PORT'" >&2; exit 1;; esac
export PATH="$HOME/.local/go/bin:$PATH"

state=".labA.json"; [ -n "$NAME" ] && state="agents/$NAME/.state.json"
if [ ! -f "$state" ]; then
  [ -n "$NAME" ] && hint="deploy it first: make new-agent NAME=$NAME FROM=labs/B/agent.yaml && make deploy-agent NAME=$NAME" \
                 || hint="finish Lab A first: make solution-part6"
  echo "ERROR: $state not found. $hint" >&2; exit 1
fi
RUNTIME_ARN=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['runtime_arn'])" "$state") \
  || { echo "ERROR: no runtime_arn in $state (deploy did not finish?)" >&2; exit 1; }
export RUNTIME_ARN

if python3 -c "import socket,sys;s=socket.socket();sys.exit(0 if s.connect_ex(('127.0.0.1',int(sys.argv[1])))==0 else 1)" "$PORT"; then
  echo "ERROR: port $PORT is already in use (an old forwarder, or another tool). See who: ss -ltnp | grep :$PORT" >&2
  echo "       use another port: make run-forwarder${NAME:+ NAME=$NAME} PORT=9000" >&2; exit 1
fi

cat <<EOF
================================================================================
 Alert forwarder on :$PORT  ->  ${RUNTIME_ARN##*/}
 This terminal stays busy (Ctrl-C stops it). In a SECOND terminal run:

   cd $ROOT
   curl -X POST localhost:$PORT/alert -d @data/alerts/inc-sip-timeout.json

 The diagnosis prints here; it can take a minute or two.
================================================================================
EOF

if command -v go >/dev/null 2>&1; then
  cd go/alert-forwarder && exec go run . -addr ":$PORT"
elif [ -x bin/alert-forwarder ]; then
  echo "(no Go toolchain: using prebuilt bin/alert-forwarder)"; exec bin/alert-forwarder -addr ":$PORT"
else
  echo "ERROR: Go not found. Run 'make go-setup' (then open a new terminal or: source ~/.bashrc), or 'make go-prebuilt' for the prebuilt binary." >&2
  exit 1
fi
