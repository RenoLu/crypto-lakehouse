.PHONY: install seed ingest silver gold quality predict api frontend test demo clean lint format

# Default Python and commands
PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest
UVICORN ?= uvicorn

install:
	$(PIP) install -e ".[dev]"
	cd frontend && npm install

seed:
	$(PYTHON) scripts/seed_demo_data.py

ingest:
	$(PYTHON) scripts/ingest_market_data.py

silver:
	$(PYTHON) scripts/build_silver.py

gold:
	$(PYTHON) scripts/build_gold.py

quality:
	$(PYTHON) scripts/run_quality_checks.py

predict:
	$(PYTHON) scripts/build_predictions.py

api:
	$(UVICORN) backend.app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm run dev

test:
	$(PYTEST) backend/tests -v --tb=short

demo: seed ingest silver gold quality
	@echo ""
	@echo "Pipeline complete. Next steps:"
	@echo "  1. Start API:  make api"
	@echo "  2. Start UI:   make frontend"
	@echo "  3. Open:       http://localhost:5173"

clean:
	rm -rf data/lakehouse/bronze/binance/*
	rm -rf data/lakehouse/silver/*
	rm -rf data/lakehouse/gold/*
	rm -f data/duckdb/lakehouse.duckdb
	rm -rf frontend/node_modules frontend/dist
	rm -rf __pycache__ backend/__pycache__ backend/app/__pycache__

lint:
	ruff check backend/
	ruff format --check backend/

format:
	ruff check --fix backend/
	ruff format backend/
