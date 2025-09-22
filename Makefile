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
	@uv run pytest tests/ -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: ts
ts:
	@uv run pytest tests/ -vs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: txs
txs:
	@uv run pytest tests/ -vxs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-api
test-api:
	@uv run pytest tests/test_user_api_async.py -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-bdd tbdd
test-bdd tbdd:
	@uv run pytest tests/features/ -v $(filter-out $@,$(MAKECMDGOALS))

# Allow arbitrary args to be passed without throwing errors
%:
	@:

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
	set -a && source .env.example && set +a && uv run granian --interface asgi src.main:app --host 0.0.0.0 --port 8000 --reload --http auto --loop uvloop --log-config src/shared/logging/granian_log_config.json --access-log

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

.PHONY: db-restart
db-restart:
	@echo "Restarting PostgreSQL container..."
	@docker restart ticketing_system_db

# Kafka
.PHONY: kafka-clean-all kca
kafka-clean-all kca:
	@echo "Deleting ALL Kafka topics..."
	@docker exec kafka1 sh -c 'for topic in $$(kafka-topics --bootstrap-server kafka1:29092 --list); do \
		echo "Deleting topic: $$topic"; \
		kafka-topics --bootstrap-server kafka1:29092 --delete --topic "$$topic" 2>/dev/null || true; \
	done'
	@echo "All topics deleted!"

.PHONY: kafka-topics kt
kafka-topics kt: kafka-clean-all
	@echo "Creating Kafka topics..."
	@docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --create --if-not-exists --topic ticketing-event --partitions 6 --replication-factor 3
	@docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --create --if-not-exists --topic ticketing-booking --partitions 6 --replication-factor 3
	@docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --create --if-not-exists --topic ticketing-ticket --partitions 6 --replication-factor 3
	@docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --create --if-not-exists --topic ticketing-booking-request --partitions 6 --replication-factor 3
	@docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --create --if-not-exists --topic ticketing-booking-response --partitions 6 --replication-factor 3
	@echo "Topics created successfully!"
	@docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --list

.PHONY: kafka-status ks
kafka-status ks:
	@echo "Kafka cluster status:"
	@docker-compose ps kafka1 kafka2 kafka3 kafka-ui
	@echo ""
	@echo "Kafka UI available at: http://localhost:8080"
	@echo "Kafka brokers at: localhost:9092,localhost:9093,localhost:9094"

# Kafka Consumers
.PHONY: consumer-start kcs
consumer-start kcs:
	@echo "Starting Kafka consumers..."
	@set -a && source .env.example && set +a && PYTHONPATH=. uv run python -m src.shared.scripts.start_consumers

.PHONY: consumer-stop kcstop
consumer-stop kcstop:
	@echo "Stopping Kafka consumers..."
	@pkill -f start_consumers || echo "No consumer processes found"

.PHONY: consumer-status kcst
consumer-status kcst:
	@echo "Consumer processes:"
	@ps aux | grep -E "(start_consumers|consumer)" | grep -v grep || echo "No consumer processes found"

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
	@echo "    make test (t) [args]     - Run all tests (accepts pytest args)"
	@echo "    make test-api [args]     - Run API tests (accepts pytest args)"
	@echo "    make test-bdd (tbdd) [args] - Run BDD tests (accepts pytest args)"
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
	@echo ""
	@echo "  Kafka & Consumers:"
	@echo "    make kafka-topics (kt)   - Create Kafka topics"
	@echo "    make kafka-status (ks)   - Check Kafka cluster status"
	@echo "    make consumer-start (kcs) - Start Kafka consumers"
	@echo "    make consumer-stop (kcstop) - Stop Kafka consumers"
	@echo "    make consumer-status (kcst) - Check consumer status"