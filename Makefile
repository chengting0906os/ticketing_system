# Database migrations
ALEMBIC_CONFIG = src/shared/alembic/alembic.ini

.PHONY: migrate-up mu
migrate-up mu:
	@echo "Running migrations..."
	@uv run alembic -c $(ALEMBIC_CONFIG) upgrade head

.PHONY: migrate-down md
migrate-down md:
	@echo "Rolling back one migration..."
	@uv run alembic -c $(ALEMBIC_CONFIG) downgrade -1

.PHONY: migrate-new mn
migrate-new mn:
	@if [ -z "$(MSG)" ]; then \
		echo "Error: Migration message required"; \
		echo "Usage: make migrate-new MSG='your message'"; \
		exit 1; \
	fi
	@echo "Creating migration: $(MSG)"
	@uv run alembic -c $(ALEMBIC_CONFIG) revision --autogenerate -m "$(MSG)"

.PHONY: migrate-history mh
migrate-history mh:
	@uv run alembic -c $(ALEMBIC_CONFIG) history

.PHONY: migrate-current mc
migrate-current mc:
	@uv run alembic -c $(ALEMBIC_CONFIG) current

# Testing
.PHONY: test t
test t:
	@uv run pytest tests/ -v

.PHONY: test-api
test-api:
	@uv run pytest tests/test_user_api_async.py -v

.PHONY: test-bdd tbdd
test-bdd tbdd:
	@uv run pytest tests/features/ -v

# Linting and formatting
.PHONY: lint
lint:
	@uv run ruff check .

.PHONY: format
format:
	@uv run ruff format .

.PHONY: pyright
pyright:
	@uv run pyright

# Development
.PHONY: run
run:
	@echo "Starting server... Press Ctrl+C to stop"
	@trap 'pkill -f granian' INT; \
	uv run granian --interface asgi src.main:app --host 0.0.0.0 --port 8000 --reload --http auto --loop uvloop

.PHONY: stop
stop:
	@echo "Stopping all granian processes..."
	@pkill -f granian || echo "No granian processes found"

.PHONY: run-prod
run-prod:
	@echo "Starting production server with multiple workers..."
	@trap 'pkill -f granian' INT; \
	uv run granian --interface asgi src.main:app --host 0.0.0.0 --port 8000 --http auto --loop uvloop --workers 4

.PHONY: clean
clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name ".DS_Store" -delete

# Docker
.PHONY: docker-up
docker-up:
	@docker-compose up -d

.PHONY: docker-down
docker-down:
	@docker-compose down

.PHONY: docker-logs
docker-logs:
	@docker-compose logs -f

.PHONY: db-shell psql
db-shell psql:
	@docker exec -it ticketing_system_db psql -U py_arch_lab -d ticketing_system_db

# Help
.PHONY: help
help:
	@echo "Available commands:"
	@echo "  Database Migrations:"
	@echo "    make migrate-up (mu)     - Run all pending migrations"
	@echo "    make migrate-down (md)   - Rollback one migration"
	@echo "    make migrate-new (mn) MSG='message' - Create new migration"
	@echo "    make migrate-history (mh) - Show migration history"
	@echo "    make migrate-current (mc) - Show current migration"
	@echo ""
	@echo "  Testing:"
	@echo "    make test (t)            - Run all tests"
	@echo "    make test-api            - Run API tests"
	@echo "    make test-bdd (tbdd)     - Run BDD tests"
	@echo ""
	@echo "  Development:"
	@echo "    make run                 - Run development server"
	@echo "    make lint                - Check code style"
	@echo "    make format              - Format code"
	@echo "    make typecheck           - Run type checking"
	@echo "    make clean               - Remove cache files"
	@echo ""
	@echo "  Docker & Database:"
	@echo "    make docker-up           - Start Docker containers"
	@echo "    make docker-down         - Stop Docker containers"
	@echo "    make docker-logs         - View Docker logs"
	@echo "    make db-shell (psql)     - Connect to PostgreSQL shell"