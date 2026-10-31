.PHONY: test smoke demo lint install live

install:
	uv sync --extra dev

test:
	uv run pytest -q

lint:
	uv run ruff check shield tests scripts web evals
	uv run ruff format --check shield tests scripts web || true

live:
	SHIELD_SPARK_REVIEW=on DEMO=live uv run python -m web.app

smoke:
	uv run python scripts/smoke.py

demo:
	@echo "Demo (3:00) — guion completo en docs/DEMO.md (replay y en vivo)."
	uv run python scripts/run_demo.py
