#!/usr/bin/env bash
# Fail fast with a clear message before `docker compose up`.
set -euo pipefail

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not reachable. Start Docker Desktop and retry." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: .env missing. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

# ports we bind on the host
PORTS=(5432 6379 6333 9000 9001 8025 8200 8081 8090 8070 4444 3001 8000 3002 9090)
busy=()
for p in "${PORTS[@]}"; do
  if (command -v ss >/dev/null && ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN) \
     || (command -v netstat >/dev/null && netstat -ano 2>/dev/null | grep -qE "[:.]$p[[:space:]].*LISTEN"); then
    busy+=("$p")
  fi
done
if [ "${#busy[@]}" -gt 0 ]; then
  echo "WARNING: ports already in use: ${busy[*]} — compose may fail to bind." >&2
fi

# disk: need a few GB free for images + volumes
avail_kb=$(df -Pk . | awk 'NR==2{print $4}')
if [ "${avail_kb:-0}" -lt 8000000 ]; then
  echo "WARNING: less than ~8 GB free on this drive." >&2
fi

echo "preflight ok"
