#!/usr/bin/env bash
# Poll `docker compose ps` until every service with a healthcheck is healthy
# (or a timeout). Services without a healthcheck only need to be running.
set -uo pipefail
TIMEOUT="${1:-300}"
deadline=$(( $(date +%s) + TIMEOUT ))

while :; do
  json=$(docker compose ps --format json 2>/dev/null)
  [ -z "$json" ] && { echo "no containers yet..."; sleep 3; continue; }
  # one JSON object per line
  bad=$(echo "$json" | python -c '
import sys, json
bad=[]
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    c=json.loads(line)
    name=c.get("Service") or c.get("Name")
    state=c.get("State"); health=c.get("Health","")
    if state!="running":
        bad.append(f"{name}:{state}")
    elif health and health not in ("healthy",""):
        bad.append(f"{name}:{health}")
print(",".join(bad))
')
  if [ -z "$bad" ]; then
    echo "all services healthy"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "TIMEOUT waiting on: $bad" >&2
    docker compose ps
    exit 1
  fi
  echo "waiting on: $bad"
  sleep 5
done
