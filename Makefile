SHELL := bash
COMPOSE := docker compose
.DEFAULT_GOAL := help

help: ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n",$$1,$$2}'

preflight: ## check docker daemon / ports / disk
	@bash scripts/preflight.sh

up: preflight ## bring up the full stack
	$(COMPOSE) up -d --build
	@bash scripts/wait_healthy.sh

up-lite: preflight ## full stack minus the observability profile
	$(COMPOSE) up -d --build
	@bash scripts/wait_healthy.sh

down: ## stop everything, keep volumes
	$(COMPOSE) down

nuke: ## stop everything and delete volumes
	$(COMPOSE) down -v

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

smoke: ## run every verify script + scenarios
	python scripts/smoke.py

scenarios: ## run the scenario catalog against the live system
	python scripts/run_scenarios.py

demo: ## seed + walk the [demo] scenarios
	python scripts/run_scenarios.py --demo

dataset: ## generate the synthetic ML dataset
	$(COMPOSE) run --rm worker python -m ml.generate_dataset

train: ## train + register the behavior risk model
	$(COMPOSE) run --rm worker python -m ml.train

loadtest: ## ~20x return volume
	python scripts/loadtest.py

backup: ## pg_dump + qdrant snapshot + minio mirror
	@bash scripts/backup.sh

restore: ## restore from backups/
	@bash scripts/restore.sh

.PHONY: help preflight up up-lite down nuke logs migrate makemigration seed vault-init smoke scenarios demo dataset train loadtest backup restore
