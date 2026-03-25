.PHONY: dev install lint db db-stop db-reset

VENV := .venv
ifeq ($(OS),Windows_NT)
  BIN := $(VENV)/Scripts
  PYTHON := python
else
  BIN := $(VENV)/bin
  PYTHON := python3
endif

dev:
	$(BIN)/uvicorn main:app --reload --host 0.0.0.0

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r requirements.txt

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

db:
	cd ../../infra && docker compose up -d

db-stop:
	cd ../../infra && docker compose down

db-reset:
	cd ../../infra && docker compose down -v && docker compose up -d
