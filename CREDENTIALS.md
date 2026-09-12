# Credentials & Local URLs

## App logins (Keycloak) — shop + dashboard, http://localhost:3000

| Email | Password | Name | Role(s) |
|---|---|---|---|
| reviewer1@returnguard.local | reviewer1 | Rita Reviewer | reviewer |
| reviewer2@returnguard.local | reviewer2 | Raj Reviewer | reviewer |
| admin1@returnguard.local | admin1 | Ada Admin | admin, reviewer |

Customers: no preset account — self-register from checkout.

## Service consoles

| Service | URL | Login |
|---|---|---|
| Shop + dashboard | http://localhost:3000 | Keycloak users above |
| FastAPI docs | http://localhost:8000/docs | none |
| Keycloak admin | http://localhost:8081 | `admin` / `KEYCLOAK_ADMIN_PASSWORD` (.env) |
| Langfuse | http://localhost:3001 | `admin@returnguard.local` / `KEYCLOAK_ADMIN_PASSWORD` (.env) |
| Qdrant | http://localhost:6333/dashboard | none |
| Bifrost (LLM gateway) | http://localhost:8090 | none |
| ContextForge (MCP gateway) | http://localhost:4444 | `admin` / `KEYCLOAK_ADMIN_PASSWORD` (.env), or `admin@returnguard.local` / same password |
| OPA | http://localhost:8181 | none |
| MinIO console | http://localhost:9001 | `returnguard` / `MINIO_ROOT_PASSWORD` (.env) |
| MailHog | http://localhost:8025 | none |
| Vault | http://localhost:8200 | dev token: `root` |
| Prometheus | http://localhost:9090 | none |
| Grafana | http://localhost:3002 | anonymous view works; login = `admin` / `KEYCLOAK_ADMIN_PASSWORD` (.env) |

Generated passwords live in `.env` (git-ignored) — regenerated fresh each
`python scripts/gen_secrets.py` run.
