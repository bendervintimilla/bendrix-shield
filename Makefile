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
	@echo "Demo (3:00) — ver docs/DEMO.md cuando H10 la deje lista."
	@echo "Por ahora: make smoke corre la prueba de humo sin red si no hay créditos."
	uv run python scripts/smoke.py --replay
