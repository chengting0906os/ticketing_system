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
	@echo "Starting unified Kafka consumers..."
	@set -a && source .env.example && set +a && PYTHONPATH=. uv run python -m src.shared.event_bus.start_unified_consumers

.PHONY: consumers-start kcss
consumers-start kcss:
	@echo "Starting multiple Kafka consumers..."
	@chmod +x src/shared/event_bus/start_multiple_consumers.sh
	@./src/shared/event_bus/start_multiple_consumers.sh $(N)

.PHONY: consumer-stop kcstop
consumer-stop kcstop:
	@echo "Stopping Kafka consumers..."
	@pkill -f start_unified_consumers || echo "No consumer processes found"

.PHONY: consumer-status kcst
consumer-status kcst:
	@echo "Consumer processes:"
	@ps aux | grep -E "(start_unified_consumers|consumer)" | grep -v grep || echo "No consumer processes found"

# Separated Consumer Architecture (New)
.PHONY: check-kafka
check-kafka:
	@echo "🔍 檢查 Kafka 服務..."
	@if nc -z localhost 9092 2>/dev/null; then \
		echo "✅ Kafka 服務正常運行"; \
	else \
		echo "❌ Kafka 服務未運行，請先啟動 Kafka"; \
		exit 1; \
	fi

.PHONY: consumers cs
consumers cs: check-kafka  ## 🚀 啟動分離的消費者架構 (推薦)
	@echo "🚀 啟動分離的消費者架構..."
	@./scripts/start_separated_consumers.sh

.PHONY: consumer-ticketing ct
consumer-ticketing ct: check-kafka  ## 🎫 啟動票務請求消費者
	@echo "🎫 啟動票務請求消費者..."
	@uv run python -m src.event_ticketing.infra.event_ticketing_mq_consumer

.PHONY: consumer-booking cb
consumer-booking cb: check-kafka  ## 📚 啟動訂單回應消費者
	@echo "📚 啟動訂單回應消費者..."
	@uv run python -m src.booking.infra.booking_mq_consumer

.PHONY: test-consumers tc
test-consumers tc:  ## 🧪 測試消費者架構
	@echo "🧪 測試消費者架構..."
	@uv run python -c "import sys; sys.path.append('src'); from event_ticketing.infra.event_ticketing_mq_consumer import EventTicketingMqConsumer; from booking.infra.booking_mq_consumer import BookingMqConsumer; print('✅ EventTicketingMqConsumer 可用'); print('✅ BookingMqConsumer 可用'); print('🎯 消費者架構測試通過!')"

.PHONY: stop-consumers sc
stop-consumers sc:  ## 🛑 停止所有消費者進程
	@echo "🛑 停止所有消費者進程..."
	@pkill -f "event_ticketing_mq_consumer" || true
	@pkill -f "booking_mq_consumer" || true
	@pkill -f "start_unified_consumers" || true
	@pkill -f "start_separated_consumers" || true
	@echo "✅ 所有消費者已停止"

.PHONY: restart-consumers rc
restart-consumers rc: stop-consumers consumers  ## 🔄 重啟所有消費者

.PHONY: consumer-architecture ca
consumer-architecture ca:  ## 📐 顯示消費者架構圖
	@echo "📐 分離消費者架構:"
	@echo "=================="
	@echo ""
	@echo "  Booking Service                   Ticketing Service"
	@echo "  ┌──────────────┐                 ┌──────────────────┐"
	@echo "  │              │                 │                  │"
	@echo "  │ Response     │◄──[response]────│                  │"
	@echo "  │ Consumer     │                 │                  │"
	@echo "  │              │                 │ Request Consumer │"
	@echo "  │              │────[request]────►│                  │"
	@echo "  │              │                 │                  │"
	@echo "  └──────────────┘                 └──────────────────┘"
	@echo ""
	@echo "Topics:"
	@echo "  • ticketing-booking-request  → Ticketing Consumer"
	@echo "  • ticketing-booking-response → Booking Consumer"

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
	@echo "    make consumer-start (kcs) - Start single Kafka consumer (old)"
	@echo "    make consumers-start (kcss) N=3 - Start multiple Kafka consumers (old)"
	@echo "    make consumer-stop (kcstop) - Stop Kafka consumers (old)"
	@echo "    make consumer-status (kcst) - Check consumer status (old)"
	@echo ""
	@echo "  Separated Consumers (New Architecture):"
	@echo "    make consumers (cs)      - 🚀 Start separated consumers (recommended)"
	@echo "    make consumer-ticketing (ct) - 🎫 Start ticketing request consumer"
	@echo "    make consumer-booking (cb) - 📚 Start booking response consumer"
	@echo "    make test-consumers (tc) - 🧪 Test consumer architecture"
	@echo "    make stop-consumers (sc) - 🛑 Stop all consumer processes"
	@echo "    make restart-consumers (rc) - 🔄 Restart all consumers"
	@echo "    make consumer-architecture (ca) - 📐 Show architecture diagram"