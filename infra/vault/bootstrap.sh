#!/bin/sh
# Runs once in the hashicorp/vault image. Loads every runtime secret into Vault
# (KV v2 at secret/returnguard/*) and creates one policy + AppRole per service.
# Role/secret ids for backend + worker are written to the shared vault_creds volume.
set -eu

export VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-root}"

echo "[vault-init] waiting for vault..."
until vault status >/dev/null 2>&1; do sleep 1; done

# dev server already mounts secret/ as kv-v2; enable is idempotent-guarded
vault secrets enable -version=2 -path=secret kv 2>/dev/null || true
vault auth enable approle 2>/dev/null || true

PG="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"

vault kv put secret/returnguard/db \
  url_async="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
  url_sync="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"

vault kv put secret/returnguard/redis url="redis://redis:6379/0"
vault kv put secret/returnguard/qdrant url="http://qdrant:6333"

vault kv put secret/returnguard/minio \
  endpoint="http://minio:9000" \
  access_key="${MINIO_ROOT_USER}" \
  secret_key="${MINIO_ROOT_PASSWORD}" \
  bucket="returnguard"

vault kv put secret/returnguard/llm \
  openai_api_key="${OPENAI_API_KEY:-}" \
  groq_api_key="${GROQ_API_KEY:-}" \
  bifrost_url="http://bifrost:8080"

vault kv put secret/returnguard/keycloak \
  issuer="http://keycloak:8080/realms/returnguard" \
  audience="returnguard-backend"

vault kv put secret/returnguard/langfuse \
  host="http://langfuse-web:3000" \
  public_key="${LANGFUSE_INIT_PROJECT_PUBLIC_KEY}" \
  secret_key="${LANGFUSE_INIT_PROJECT_SECRET_KEY}"

vault kv put secret/returnguard/mcp gateway_url="http://mcp-gateway:4444"

# ---- per-service policy + AppRole -------------------------------------------
for SVC in backend worker; do
  cat > /tmp/${SVC}.hcl <<EOF
path "secret/data/returnguard/*" { capabilities = ["read"] }
path "auth/token/lookup-self"    { capabilities = ["read"] }
EOF
  vault policy write "rg-${SVC}" /tmp/${SVC}.hcl
  vault write "auth/approle/role/${SVC}" \
    token_policies="rg-${SVC}" token_ttl=1h token_max_ttl=4h secret_id_ttl=0 secret_id_num_uses=0
  RID=$(vault read -field=role_id "auth/approle/role/${SVC}/role-id")
  SID=$(vault write -f -field=secret_id "auth/approle/role/${SVC}/secret-id")
  {
    echo "VAULT_ROLE_ID=${RID}"
    echo "VAULT_SECRET_ID=${SID}"
  } > "/vault-creds/${SVC}.env"
  echo "[vault-init] wrote /vault-creds/${SVC}.env"
done

echo "[vault-init] done"
