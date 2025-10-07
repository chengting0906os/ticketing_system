# Database operations
ALEMBIC_CONFIG = src/platform/alembic/alembic.ini

.PHONY: reset reset-all reset-db seed
reset:
	@echo "🚀 Complete system reset (Kafka + Database)..."
	@echo "Step 1: Resetting Kafka..."
	@PYTHONPATH=. uv run python script/reset_kafka.py
	@echo ""
	@echo "Step 2: Resetting Database..."
	@PYTHONPATH=. uv run python script/reset_database.py
	@echo ""
	@echo "Step 3: Seeding test data..."
	@PYTHONPATH=. uv run python script/seed_data.py
	@echo "✅ Complete system reset finished!"
	@echo ""
	@echo "💡 Tip: Run 'make services' to start consumers, or use 'make reset-all' next time"

reset-all:  ## 🔄 Reset system and start services (one-stop command)
	@echo "🚀 Complete system reset + service launch..."
	@$(MAKE) reset
	@echo ""
	@echo "Step 4: Starting consumers..."
	@$(MAKE) services

reset-db:
	@echo "🔄 Resetting database structure..."
	@PYTHONPATH=. uv run python script/reset_database.py

seed:
	@echo "🌱 Seeding test data..."
	@PYTHONPATH=. uv run python script/seed_data.py

# Database migrations

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
	@uv run pytest test/ -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: ts
ts:
	@uv run pytest test/ -vs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: txs
txs:
	@uv run pytest test/ -vxs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-api
test-api:
	@uv run pytest test/test_user_api_async.py -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-bdd tbdd
test-bdd tbdd:
	@uv run pytest test/features/ -v $(filter-out $@,$(MAKECMDGOALS))

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

.PHONY: pyrefly pyre
pyrefly pyre:
	@uv run pyrefly check

# Development
.PHONY: run
run:
	@echo "Starting server with auto-reload... Press Ctrl+C to stop"
	@trap 'pkill -f granian' INT; \
	set -a && source .env.example && set +a && \
	GRANIAN_RELOAD=true \
	GRANIAN_RELOAD_PATHS=src \
	GRANIAN_HOST=0.0.0.0 \
	GRANIAN_PORT=8000 \
	GRANIAN_INTERFACE=asgi \
	GRANIAN_HTTP=auto \
	GRANIAN_LOOP=uvloop \
	GRANIAN_LOG_CONFIG=src/platform/logging/granian_log_config.json \
	GRANIAN_ACCESS_LOG=true \
	uv run granian src.main:app

.PHONY: stop-granian
stop-granian:
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
.PHONY: clean-all ca
clean-all ca:
	@echo "🧹 Complete system cleanup (ALL topics, consumer groups, RocksDB state)..."
	@PYTHONPATH=. uv run python script/clean_all.py

.PHONY: kafka-clean kc
kafka-clean kc:
	@echo "🧹 Cleaning ALL Kafka topics and consumer groups..."
	@PYTHONPATH=. python script/reset_kafka.py

.PHONY: kafka-clean-topics kct
kafka-clean-topics kct:
	@echo "🧹 Deleting ALL Kafka topics only..."
	@docker exec kafka1 sh -c 'for topic in $$(kafka-topics --bootstrap-server kafka1:29092 --list); do \
		kafka-topics --bootstrap-server kafka1:29092 --delete --topic "$$topic" 2>/dev/null || true; \
	done'
	@echo "✅ All topics deleted"

.PHONY: kafka-status ks
kafka-status ks:
	@echo "📊 Kafka Status:"
	@docker-compose ps kafka1 kafka2 kafka3 kafka-ui
	@echo ""
	@echo "🌐 Kafka UI: http://localhost:8080"
	@echo "🔗 Brokers: localhost:9092,9093,9094"


# Services
.PHONY: check-kafka
check-kafka:
	@if ! nc -z localhost 9092 2>/dev/null; then \
		echo "❌ Kafka 服務未運行，請先啟動 Kafka"; \
		exit 1; \
	fi

.PHONY: services ss
services ss: check-kafka  ## 🚀 智能啟動活動服務 (從資料庫選擇)
	@echo "🚀 啟動智能活動服務選擇器..."
	@PYTHONPATH=. uv run python script/launch_all_consumers.py


.PHONY: stop-services stop
stop-services stop:  ## 🛑 停止所有服務
	@echo "🛑 停止所有服務..."
	@pkill -f "seat_reservation_mq_consumer" || true
	@pkill -f "ticketing_mq_consumer" || true
	@pkill -f "launch_all_consumers" || true
	@echo "✅ 所有服務已停止"

.PHONY: restart-services restart
restart-services restart: stop-services services  ## 🔄 重啟所有服務

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
	@echo "    make test (t) [args]     - Run all test (accepts pytest args)"
	@echo "    make test-api [args]     - Run API test (accepts pytest args)"
	@echo "    make test-bdd (tbdd) [args] - Run BDD test (accepts pytest args)"
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
	@echo "  Cleanup & Reset:"
	@echo "    make reset               - 🔄 Reset Kafka + Database + Seed data"
	@echo "    make reset-all           - 🚀 Reset + Auto-start services (one-stop!)"
	@echo "    make clean-all (ca)      - 🧹 Complete cleanup (topics, groups, RocksDB)"
	@echo "    make kafka-clean (kc)    - Clean all Kafka topics"
	@echo "    make kafka-status (ks)   - Check Kafka cluster status"
	@echo ""
	@echo "  Services:"
	@echo "    make services (ss)       - 🚀 Start services (interactive event selection)"
	@echo "    make stop                - 🛑 Stop all services"
	@echo "    make restart             - 🔄 Restart all services"
	@echo "    make mkt EVENT_ID=1      - 📊 Monitor Kafka topics for event"