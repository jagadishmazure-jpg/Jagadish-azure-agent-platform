.PHONY: install lint test evals cards bicep demo orchestrations mesh compose foundry-dry-run seed-dry-run
install:          ## venv + dev extras
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
lint:
	ruff check . && ruff format --check .
test:
	pytest -q
evals:            ## golden-set evals + release gate (offline)
	python scripts/run_evals.py
cards:            ## regenerate control-plane/agent-cards
	python scripts/export_agent_cards.py
bicep:
	az bicep build --file infra/main.bicep --stdout > /dev/null
demo:             ## in-process demo: three loans end to end
	python scripts/demo.py
orchestrations:   ## five MAF orchestration patterns + comparison (offline)
	python scripts/orchestrations_demo.py && python scripts/orchestrations_demo.py --compare
mesh:             ## every service as its own process over HTTP (no Docker)
	./scripts/run_local_mesh.sh
compose:
	docker compose up --build
foundry-dry-run:
	python scripts/foundry_register.py --dry-run
seed-dry-run:
	python scripts/seed_search_index.py --dry-run
