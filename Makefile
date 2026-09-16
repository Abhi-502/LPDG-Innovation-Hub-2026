.PHONY: help run validate test api docker-build docker-run clean

DATA_DIR ?= ./data
OUT_FILE ?= predictions.csv
HOST ?= 0.0.0.0
PORT ?= 8000
IMAGE_NAME ?= gateway-prioritisation-api:latest

help:
	@echo "Available commands:"
	@echo "  make run          - Execute Part 1 CLI pipeline to generate $(OUT_FILE)"
	@echo "  make validate     - Validate $(OUT_FILE) using official validator"
	@echo "  make test         - Run full automated test suite"
	@echo "  make api          - Start the FastAPI web application server"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run API in isolated Docker container"
	@echo "  make clean        - Remove temporary artifacts and test caches"

run:
	python3 main.py --data $(DATA_DIR) --out $(OUT_FILE)

validate:
	python3 validate_submission.py $(OUT_FILE)

test:
	python3 -m pytest -v tests/

api:
	python3 main.py --serve --host $(HOST) --port $(PORT)

docker-build:
	docker build -t $(IMAGE_NAME) .

docker-run:
	docker run --rm -p $(PORT):$(PORT) -v $(PWD)/data:/app/data:ro $(IMAGE_NAME)

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf .coverage artifacts/runs/* artifacts/.run.lock
