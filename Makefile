.PHONY: setup test lint format train-seg ingest-code validate-rules budget baselines eval api up web

# Targets that belong to a later milestone fail loudly instead of doing nothing.
define NOT_YET
	@echo "make $@: not implemented yet (milestone $(1), see docs/PROJECT_SPEC.md §15)"; exit 1
endef

setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:
	uv run ruff check --fix .
	uv run ruff format .

validate-rules:
	uv run python -m plancheck.compliance.registry

budget:
	$(call NOT_YET,M2)

train-seg:
	$(call NOT_YET,M3)

api up:
	$(call NOT_YET,M6)

web:
	$(call NOT_YET,M7)

ingest-code baselines:
	$(call NOT_YET,M8)

eval:
	$(call NOT_YET,M4)
