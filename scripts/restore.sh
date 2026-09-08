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

if [ -d "$DIR/minio" ]; then
  echo "[restore] minio objects from $DIR/minio"
  # docker cp into a short-lived named mc container, then mirror back to the
  # bucket (the mc image has no tar, and Windows bind-mounts are unreliable).
  CID="rg-restore-mc-$(date +%s)"
  docker compose run -d --name "$CID" --entrypoint sleep minio-init 300 >/dev/null
  docker cp "$DIR/minio/." "$CID:/tmp/m"
  docker exec "$CID" sh -c \
    "mc alias set l http://minio:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD >/dev/null && mc mirror --overwrite /tmp/m l/returnguard"
  docker rm -f "$CID" >/dev/null
fi

echo "[restore] restart app"
docker compose restart backend worker
echo "[restore] done"
