.PHONY: dev install db db-stop db-reset

dev:
	.venv/bin/uvicorn main:app --reload

install:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

db:
	cd ../../infra && docker compose up -d

db-stop:
	cd ../../infra && docker compose down

db-reset:
	cd ../../infra && docker compose down -v && docker compose up -d
