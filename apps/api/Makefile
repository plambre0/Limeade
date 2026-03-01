.PHONY: dev install lint db db-stop db-reset

dev:
	.venv/bin/uvicorn main:app --reload --host 0.0.0.0

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

db:
	cd ../../infra && docker compose up -d

db-stop:
	cd ../../infra && docker compose down

db-reset:
	cd ../../infra && docker compose down -v && docker compose up -d
