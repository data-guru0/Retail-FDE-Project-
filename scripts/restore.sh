#!/usr/bin/env bash
# restore.sh backups/<timestamp>
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:?usage: restore.sh backups/<timestamp>}"

echo "[restore] postgres from $DIR/returnguard.dump"
docker compose exec -T postgres dropdb -U returnguard --if-exists --force returnguard
docker compose exec -T postgres createdb -U returnguard returnguard
docker compose exec -T postgres pg_restore -U returnguard -d returnguard < "$DIR/returnguard.dump"

if [ -f "$DIR/qdrant-policy_docs.snapshot" ]; then
  echo "[restore] qdrant policy_docs"
  curl -s -X POST "http://localhost:6333/collections/policy_docs/snapshots/upload?priority=snapshot" \
    -H "Content-Type: multipart/form-data" \
    -F "snapshot=@$DIR/qdrant-policy_docs.snapshot" >/dev/null || \
    echo "[restore] qdrant upload failed — re-run: make reembed-policy"
fi

echo "[restore] restart app"
docker compose restart backend worker
echo "[restore] done"
