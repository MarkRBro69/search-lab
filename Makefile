.PHONY: dev test lint format install docker-up docker-down docker-logs clean

# Run development server with hot-reload
dev:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run all tests
test:
	uv run pytest

# Run tests with coverage report
test-cov:
	uv run pytest --cov=src --cov-report=term-missing

# Lint code
lint:
	uv run ruff check .

# Lint and auto-fix
lint-fix:
	uv run ruff check . --fix

# Format code
format:
	uv run ruff format .

# Check formatting without applying (CI)
format-check:
	uv run ruff format --check .

# Install all dependencies including dev
install:
	uv sync --all-extras

# Install pre-commit hooks
hooks:
	uv run pre-commit install

# Start all infrastructure services
docker-up:
	docker-compose up -d

# Start only OpenSearch
docker-up-os:
	docker-compose up -d opensearch

# Stop all services
docker-down:
	docker-compose down

# View logs
docker-logs:
	docker-compose logs -f

# Remove build artifacts and caches
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	echo "Clean done"
