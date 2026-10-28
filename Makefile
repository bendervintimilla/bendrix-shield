.PHONY: test smoke demo lint install

install:
	uv sync --extra dev

test:
	uv run pytest -q

lint:
	uv run ruff check shield tests scripts
	uv run ruff format --check shield tests scripts || true

smoke:
	uv run python scripts/smoke.py

demo:
	@echo "Demo (3:00) — guion completo en docs/DEMO.md (replay y en vivo)."
	uv run python scripts/smoke.py --replay
