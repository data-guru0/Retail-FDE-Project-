SHELL := bash
COMPOSE := docker compose
.DEFAULT_GOAL := help

help: ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n",$$1,$$2}'

preflight: ## check docker daemon / ports / disk
	@bash scripts/preflight.sh

up: preflight ## bring up the full stack (incl. Prometheus + Grafana)
	$(COMPOSE) --profile observability up -d --build
	@bash scripts/wait_healthy.sh

up-lite: preflight ## full stack minus the observability profile
	$(COMPOSE) up -d --build
	@bash scripts/wait_healthy.sh

down: ## stop everything, keep volumes
	$(COMPOSE) --profile observability --profile load down

nuke: ## stop everything and delete volumes
	$(COMPOSE) --profile observability --profile load down -v

logs: ## tail logs
	$(COMPOSE) logs -f --tail=100

migrate: ## run alembic migrations in the backend container
	$(COMPOSE) run --rm backend alembic upgrade head

makemigration: ## autogenerate a migration: make makemigration m="msg"
	$(COMPOSE) run --rm backend alembic revision --autogenerate -m "$(m)"

seed: ## load real products + policy docs
	$(COMPOSE) run --rm backend python -m seed.seed

vault-init: ## re-run the vault bootstrap
	$(COMPOSE) run --rm vault-init

opa-test: ## run the OPA policy unit tests (infra/opa/*_test.rego)
	$(COMPOSE) exec -T opa /opa test /policies -v

smoke: ## run every verify script
	python scripts/smoke.py

dataset: ## generate the synthetic ML dataset
	$(COMPOSE) run --rm worker python -m ml.generate_dataset

train: ## train + register the behavior risk model
	$(COMPOSE) run --rm worker python -m ml.train

reembed-policy: ## embed the active policy docs into Qdrant
	$(COMPOSE) run --rm worker python -m pipeline.policy_index

sync-prompts: ## push worker/pipeline/prompts/*.md to Langfuse (versioned, UI-editable)
	$(COMPOSE) run --rm worker python -m pipeline.sync_prompts

replay: ## re-run ONE pipeline node for a past run: make replay a="<graph_run_id> <node>"
	$(COMPOSE) run --rm worker python replay.py $(a)

reprocess: ## batch re-review a window of open returns: make reprocess a="--since 2026-08-01 --dry-run"
	$(COMPOSE) run --rm worker python reprocess.py $(a)

mcp-setup: ## configure ContextForge: gateway + per-agent virtual servers
	python scripts/mcp_setup.py

bifrost-setup: ## register per-agent Bifrost virtual keys (model scope + budget + rate limit)
	python scripts/bifrost_setup.py

m4-setup: dataset train reembed-policy mcp-setup bifrost-setup sync-prompts ## everything the M4+ pipeline needs
	$(COMPOSE) restart worker   # pick up the fresh model + Vault-side ContextForge/Bifrost wiring
	@echo "setup complete (dataset + model + policy index + ContextForge + Bifrost VKs + prompts)"

loadtest: ## ~20x return volume
	python scripts/loadtest.py

backup: ## pg_dump + qdrant snapshot + minio mirror
	@bash scripts/backup.sh

restore: ## restore from backups/
	@bash scripts/restore.sh

.PHONY: help preflight up up-lite down nuke logs migrate makemigration seed vault-init opa-test smoke dataset train loadtest backup restore reembed-policy sync-prompts replay reprocess mcp-setup bifrost-setup m4-setup
