.PHONY: setup test lint format train-seg ingest-code validate-rules budget baselines eval eval-explain eval-explain-report api up web demo

# Targets that belong to a later milestone fail loudly instead of doing nothing.
define NOT_YET
	@echo "make $@: not implemented yet (milestone $(1), see docs/PROJECT_SPEC.md §15)"; exit 1
endef

setup:
	uv sync

# The coverage gate lives here, not in pytest's default options, so running one test file
# with plain pytest does not trip it. Line and branch coverage of plancheck/ (pyproject.toml).
COVERAGE_MIN := 90

test:
	uv run python -m pytest --cov --cov-fail-under=$(COVERAGE_MIN)

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
	uv run python -m plancheck.evaluation.explain_eval check

# Calls the language model (OPENROUTER_API_KEY), then rewrites eval/rag/citation_labels.yaml,
# keeping every label already given, and eval/reports/explanation-eval.md.
eval-explain:
	uv run python -m plancheck.evaluation.explain_eval run --runs 3

# Recomputes the explanation report from the saved runs and the labels. No model call.
eval-explain-report:
	uv run python -m plancheck.evaluation.explain_eval report

demo:
	uv run python -m plancheck.demo
