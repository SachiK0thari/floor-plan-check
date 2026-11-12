.PHONY: setup test lint format train-seg ingest-code validate-rules budget baselines eval api up web demo

# Targets that belong to a later milestone fail loudly instead of doing nothing.
define NOT_YET
	@echo "make $@: not implemented yet (milestone $(1), see docs/PROJECT_SPEC.md §15)"; exit 1
endef

setup:
	uv sync

test:
	uv run python -m pytest

lint:
	uv run python -m ruff check .
	uv run python -m ruff format --check .
	uv run python -m mypy

format:
	uv run python -m ruff check --fix .
	uv run python -m ruff format .

validate-rules:
	uv run python -m plancheck.compliance.registry

budget:
	uv run python -m plancheck.evaluation.budget

train-seg:
	$(call NOT_YET,M3)

api up:
	$(call NOT_YET,M6)

web:
	uv run python -m plancheck.web

ingest-code baselines:
	$(call NOT_YET,M8)

eval:
	uv run python -m plancheck.evaluation.validate

demo:
	uv run python -m plancheck.demo
