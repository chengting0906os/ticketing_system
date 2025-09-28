# Database operations
ALEMBIC_CONFIG = src/shared/alembic/alembic.ini

.PHONY: reset-db
reset-db:
	@echo "🚀 Resetting database with test data..."
	@python -m scripts.reset_database

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
.PHONY: kafka-clean kc
kafka-clean kc:
	@echo "🧹 Deleting ALL Kafka topics..."
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
	@PYTHONPATH=. uv run python scripts/launch_all_consumers.py


.PHONY: stop-services stop
stop-services stop:  ## 🛑 停止所有服務
	@echo "🛑 停止所有服務..."
	@pkill -f "rocksdb_seat_processor" || true
	@pkill -f "booking_mq_consumer" || true
	@pkill -f "seat_reservation_consumer" || true
	@pkill -f "event_ticketing_mq_consumer" || true
	@pkill -f "launch_all_consumers" || true
	@echo "✅ 所有服務已停止"

.PHONY: restart-services restart
restart-services restart: stop-services services  ## 🔄 重啟所有服務

.PHONY: architecture arch
architecture arch:  ## 📐 顯示架構圖
	@echo "📐 三微服務分散式架構 (50,000張票 + RocksDB + 無鎖預訂):"
	@echo "================================================================"
	@echo ""
	@echo "┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐"
	@echo "│   booking_service   │     │   seat_reservation   │     │   event_ticketing   │"
	@echo "│    (PostgreSQL)     │     │      (RocksDB)       │     │     (PostgreSQL)    │"
	@echo "└─────────────────────┘     └──────────────────────┘     └─────────────────────┘"
	@echo "         │                           │                          │"
	@echo "         │                           │                          │"
	@echo "         ▼                           ▼                          ▼"
	@echo "┌─────────────────────────────────────────────────────────────────────────────┐"
	@echo "│                             Kafka + Quix Streams                            │"
	@echo "│                   Event-Driven + Stateful Stream + Lock-Free                │"
	@echo "└─────────────────────────────────────────────────────────────────────────────┘"
	@echo ""
	@echo "流程："
	@echo "  1. booking_service 創建訂單 → 發送 TicketReservedRequest"
	@echo "  2. seat_reservation 選座位 → RocksDB 原子操作"
	@echo "  3. RocksDB 成功 → 雙事件發送 (到 booking + event_ticketing)"
	@echo "  4. booking_service 狀態 PROCESSING → PENDING_PAYMENT (Redis TTL 15分)"
	@echo "  5. event_ticketing 票據狀態 AVAILABLE → RESERVED"
	@echo ""
	@echo "Topics (支援 event-id-{event_id}-* 格式)："
	@echo "  Global Topics:"
	@echo "    • seat-commands              → RocksDB Processor"
	@echo "    • seat-results               → seat_reservation"
	@echo "    • booking-events             → seat_reservation"
	@echo "    • seat-reservation-results   → booking_service"
	@echo "    • ticket-status-updates      → event_ticketing"
	@echo ""
	@echo "  Event-Specific Topics:"
	@echo "    • event-id-{event_id}-seat-commands"
	@echo "    • event-id-{event_id}-seat-results"
	@echo "    • event-id-{event_id}-booking-events"
	@echo "    • event-id-{event_id}-seat-reservation-results"
	@echo "    • event-id-{event_id}-ticket-status-updates"
	@echo ""
	@echo "  使用方式: make kafka-topics-event EVENT_ID=123"

.PHONY: consumer-architecture ca
consumer-architecture ca: architecture  ## 📐 顯示架構圖 (別名)

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
	@echo "  Kafka:"
	@echo "    make kafka-clean (kc)    - Clean all Kafka topics"
	@echo "    make kafka-status (ks)   - Check Kafka cluster status"
	@echo ""
	@echo "  Services:"
	@echo "    make services (ss)       - 🚀 Start services (interactive event selection)"
	@echo "    make stop                - 🛑 Stop all services"
	@echo "    make restart             - 🔄 Restart all services"
	@echo "    make architecture (arch) - 📐 Show architecture diagram"