#!/usr/bin/env bash
# pg_dump + Qdrant snapshot + MinIO mirror -> backups/<timestamp>/
set -euo pipefail
cd "$(dirname "$0")/.."
TS=$(date +%Y%m%d-%H%M%S)
OUT="backups/$TS"
mkdir -p "$OUT"

echo "[backup] postgres"
docker compose exec -T postgres pg_dump -U returnguard -Fc returnguard > "$OUT/returnguard.dump"

echo "[backup] qdrant snapshot"
curl -s -X POST "http://localhost:6333/collections/policy_docs/snapshots" >/dev/null || true
NAME=$(curl -s "http://localhost:6333/collections/policy_docs/snapshots" \
  | python -c "import sys,json;d=json.load(sys.stdin);print(d['result'][-1]['name'])" 2>/dev/null || echo "")
if [ -n "$NAME" ]; then
  curl -s "http://localhost:6333/collections/policy_docs/snapshots/$NAME" -o "$OUT/qdrant-policy_docs.snapshot"
fi

echo "[backup] minio mirror"
# Mirror inside a named (not --rm) container, then `docker cp` it out and remove
# it. Bind-mounting a host path into `compose run` is unreliable on Windows
# Docker Desktop (drive-letter / space mangling), so we copy instead.
CID="rg-backup-mc-$TS"
docker compose run -T --name "$CID" --entrypoint sh minio-init -c \
  "mc alias set l http://minio:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD >/dev/null && mc mirror --overwrite l/returnguard /tmp/mirror"
docker cp "$CID:/tmp/mirror" "$OUT/minio"
docker rm -f "$CID" >/dev/null
echo "[backup] minio objects: $(find "$OUT/minio" -type f | wc -l)"

echo "[backup] done -> $OUT"
