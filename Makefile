# Database operations
ALEMBIC_CONFIG = alembic.ini

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
	@uv run pytest test/ --ignore=test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: ts
ts:
	@uv run pytest test/ --ignore=test/service/e2e -vs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: txs
txs:
	@uv run pytest test/ --ignore=test/service/e2e -vxs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-e2e te2e
test-e2e te2e:
	@uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

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

# Docker - Infrastructure Only
.PHONY: docker-up
docker-up:
	@echo "🐳 Starting infrastructure services (DB, Kafka, Kvrocks, Monitoring)..."
	@docker-compose up -d postgres kafka1 kafka2 kafka3 kafka-ui kvrocks prometheus grafana loki promtail

.PHONY: docker-down
docker-down:
	@echo "🛑 Stopping all Docker services..."
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

# Docker - Full Stack (Infrastructure + Application)
.PHONY: docker-stack-up dsu
docker-stack-up dsu:  ## 🚀 Start complete containerized stack (infrastructure + app services)
	@echo "🚀 Building and starting complete stack..."
	@docker-compose build
	@docker-compose up -d
	@echo ""
	@echo "✅ Stack started! Access points:"
	@echo "   🌐 API:        http://localhost:8000"
	@echo "   📚 API Docs:   http://localhost:8000/docs"
	@echo "   📊 Kafka UI:   http://localhost:8080"
	@echo "   📈 Grafana:    http://localhost:3000 (admin/admin)"
	@echo "   🔍 Prometheus: http://localhost:9090"
	@echo ""
	@echo "📖 Full guide: see DOCKER_GUIDE.md"

.PHONY: docker-stack-down dsd
docker-stack-down dsd:  ## 🛑 Stop complete stack
	@docker-compose down

.PHONY: docker-stack-restart dsr
docker-stack-restart dsr:  ## 🔄 Restart application services (keep infrastructure running)
	@echo "🔄 Restarting application services..."
	@docker-compose restart ticketing-api ticketing-consumer seat-reservation-consumer

.PHONY: docker-app-logs dal
docker-app-logs dal:  ## 📋 View application service logs
	@docker-compose logs -f ticketing-api ticketing-consumer seat-reservation-consumer

.PHONY: docker-api-logs dlog
docker-api-logs dlog:  ## 📋 View API logs only
	@docker-compose logs -f ticketing-api

.PHONY: docker-rebuild dr
docker-rebuild dr:  ## 🔨 Rebuild and restart application services
	@echo "🔨 Rebuilding application services..."
	@docker-compose build ticketing-api ticketing-consumer seat-reservation-consumer
	@docker-compose up -d ticketing-api ticketing-consumer seat-reservation-consumer

.PHONY: docker-shell dsh
docker-shell dsh:  ## 🐚 Enter API container shell
	@docker-compose exec ticketing-api bash

.PHONY: docker-test dt
docker-test dt:  ## 🧪 Run tests in container
	@docker-compose exec ticketing-api uv run pytest test/ --ignore=test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: docker-test-e2e dte2e de2e
docker-test-e2e dte2e de2e:  ## 🧪 Run E2E tests in container
	@docker-compose exec ticketing-api uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: docker-test-all dta
docker-test-all dta:  ## 🧪 Run all tests (including E2E) in container
	@docker-compose exec ticketing-api uv run pytest test/ -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: docker-migrate dm
docker-migrate dm:  ## 🗄️ Run migrations in container
	@docker-compose exec ticketing-api uv run alembic upgrade head

.PHONY: docker-seed ds
docker-seed ds:  ## 🌱 Seed data in container
	@docker-compose exec ticketing-api sh -c "PYTHONPATH=/app uv run python script/seed_data.py"

.PHONY: docker-clean dc
docker-clean dc:  ## 🧹 Remove all containers, volumes, and images
	@echo "⚠️  This will remove ALL data. Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] && docker-compose down -v --rmi all || echo "Cancelled"

.PHONY: docker-clean-all dca
docker-clean-all dca:  ## 🧹 Clean Kafka topics, consumer groups, and Kvrocks (in container)
	@echo "🧹 Cleaning Kafka + Kvrocks in Docker..."
	@docker-compose exec ticketing-api sh -c "PYTHONPATH=/app uv run python script/clean_all.py"

.PHONY: docker-reset dre
docker-reset dre:  ## 🔄 Reset database (migrate + seed)
	@echo "🔄 Resetting database..."
	@$(MAKE) docker-migrate
	@$(MAKE) docker-seed

# Consumer scaling parameters (can be overridden: make dra SEAT_CONSUMERS=5)
SEAT_CONSUMERS ?= 1
TICKETING_CONSUMERS ?= 1

.PHONY: docker-scale-consumers dsc
docker-scale-consumers dsc:  ## 📈 Scale consumers to specified replicas
	@echo "📈 Scaling consumers..."
	@echo "   🪑 Seat Reservation: $(SEAT_CONSUMERS) instances"
	@echo "   🎫 Ticketing: $(TICKETING_CONSUMERS) instances"
	@docker-compose up -d --scale seat-reservation-consumer=$(SEAT_CONSUMERS) --scale ticketing-consumer=$(TICKETING_CONSUMERS) --no-recreate

.PHONY: docker-reset-all dra
docker-reset-all dra:  ## 🚀 Complete Docker reset (down → up → migrate → seed → scale consumers)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo ""
	@echo "🔧 Configuration:"
	@echo "   🪑 Seat Reservation Consumers: $(SEAT_CONSUMERS)"
	@echo "   🎫 Ticketing Consumers: $(TICKETING_CONSUMERS)"
	@echo ""
	@echo "⚠️  This will:"
	@echo "   1. Stop and remove all containers + volumes (cleans Kafka/Kvrocks automatically)"
	@echo "   2. Start all services (Docker handles dependencies via healthchecks)"
	@echo "   3. Reset database (migrate + seed)"
	@echo "   4. Start $(SEAT_CONSUMERS) seat-reservation + $(TICKETING_CONSUMERS) ticketing consumers"
	@echo ""
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "Step 1/4: Stopping and removing old environment..."
	@docker-compose down -v
	@echo ""
	@echo "Step 2/4: Starting all services (dependencies handled by Docker)..."
	@docker-compose up -d
	@echo "⏳ Waiting for services to be healthy..."
	@timeout 60 sh -c 'until docker-compose exec -T ticketing-api curl -sf http://localhost:8000/health > /dev/null 2>&1; do sleep 2; done' || (echo "⚠️  API not ready yet, but continuing..." && true)
	@echo ""
	@echo "Step 3/4: Resetting database (migrate + seed)..."
	@$(MAKE) docker-migrate
	@$(MAKE) docker-seed
	@echo ""
	@echo "Step 4/4: Starting consumers..."
	@$(MAKE) docker-scale-consumers SEAT_CONSUMERS=$(SEAT_CONSUMERS) TICKETING_CONSUMERS=$(TICKETING_CONSUMERS)
	@echo ""
	@echo "✅ ==================== RESET COMPLETED ===================="
	@echo ""
	@echo "🌐 Access Points:"
	@echo "   API:        http://localhost:8000"
	@echo "   API Docs:   http://localhost:8000/docs"
	@echo "   Kafka UI:   http://localhost:8080"
	@echo "   Grafana:    http://localhost:3000"
	@echo ""
	@echo "📋 View logs:  make docker-app-logs"
	@echo "🧪 Run tests:  make docker-test"

# Load Testing
.PHONY: loadtest-build ltb
loadtest-build ltb:  ## 🔨 Build load test binary
	@echo "🔨 Building load test binary..."
	@cd script/go_client && go build -o loadtest main.go
	@echo "✅ Load test binary built: script/go_client/loadtest"

.PHONY: loadtest-quick ltq
loadtest-quick ltq:  ## ⚡ Quick load test: 1,000 requests (10 users)
	@echo "⚡ Running quick test (1K requests, 10 users)..."
	@cd script/go_client && ./loadtest -requests 25 -concurrency 5


.PHONY: loadtest-full ltf
loadtest-full ltf:  ## 💪 Full load test: 50,000 requests (10 users)
	@echo "💪 Running full load test (50K requests, 10 users)..."
	@cd script/go_client && ./loadtest -requests 50000 -concurrency 100

.PHONY: loadtest-docker ltd
loadtest-docker ltd:  ## 🐳 Test Docker environment: 5,000 requests
	@echo "🐳 Testing Docker environment..."
	@cd script/go_client && ./loadtest -host http://localhost:8000 -requests 5000 -concurrency 100

.PHONY: loadtest-help lth
loadtest-help lth:  ## 📖 Show load test documentation
	@echo "📋 Load Test Commands:"
	@echo "  ltb   - Build load test binary"
	@echo "  ltq   - Quick test (1K requests)"
	@echo "  ltm   - Medium test (10K requests)"
	@echo "  ltf   - Full test (50K requests)"
	@echo "  ltx   - Stress test (100K requests)"
	@echo "  ltmix - Mixed mode (80% auto, 20% manual)"
	@echo "  ltd   - Docker test (5K requests)"
	@echo ""
	@echo "💡 Before running tests:"
	@echo "  make seed         - Setup test data (12 users + 3K tickets)"
	@echo "  make docker-seed  - Setup in Docker"

# Kafka
# Note: seed_data.py now creates ~3K tickets by default (suitable for development/testing)

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
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           📋 Ticketing System - Makefile Commands            ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "🚀 QUICK START"
	@echo "  make dra [SEAT_CONSUMERS=N]  - Docker: Complete reset + scale consumers"
	@echo "  make reset-all               - Local: Reset Kafka + DB + start consumers"
	@echo "  make help-full               - Show detailed command documentation"
	@echo ""
	@echo "🐳 DOCKER (Recommended)"
	@echo "  Complete Workflows:"
	@echo "    dra  - Complete reset (down→up→clean→migrate→seed→scale)"
	@echo "    dca  - Clean Kafka + Kvrocks only"
	@echo "    dre  - Reset database only"
	@echo "    dsc  - Scale consumers"
	@echo "  Stack:"
	@echo "    dsu  - Start stack        dsd  - Stop stack"
	@echo "    dsr  - Restart services   dr   - Rebuild containers"
	@echo "  Testing:"
	@echo "    dt   - Run tests          de2e - Run E2E tests"
	@echo "    dta  - Run all tests"
	@echo "  Database:"
	@echo "    dm   - Migrate            ds   - Seed data"
	@echo "  Logs:"
	@echo "    dal  - App logs           dlog - API logs"
	@echo "    dsh  - Enter shell"
	@echo ""
	@echo "🧪 TESTING (Local)"
	@echo "    t    - Run unit tests     te2e - Run E2E tests"
	@echo "    ts   - With output (-s)   txs  - Stop on fail (-xs)"
	@echo "    tbdd - Run BDD tests"
	@echo ""
	@echo "🗄️  DATABASE"
	@echo "    mu   - Migrate up         md   - Migrate down"
	@echo "    mn   - New migration      mh   - History"
	@echo "    psql - PostgreSQL shell"
	@echo ""
	@echo "🌊 KAFKA"
	@echo "    ca   - Clean all (Kafka+Kvrocks+DB+RocksDB)"
	@echo "    kc   - Clean Kafka only   ks   - Kafka status"
	@echo ""
	@echo "⚡ LOAD TESTING"
	@echo "    ltb  - Build binary       lth  - Show help"
	@echo "    ltq  - Quick (1K)         ltm  - Medium (10K)"
	@echo "    ltf  - Full (50K)         ltx  - Stress (100K)"
	@echo "    ltmix- Mixed mode         ltd  - Docker test"
	@echo ""
	@echo "🎫 SERVICES (Local)"
	@echo "    ss   - Start consumers    stop - Stop consumers"
	@echo ""
	@echo "🔧 DEVELOPMENT"
	@echo "    run    - Start API server"
	@echo "    lint   - Check style      format - Fix style"
	@echo "    pyre   - Type check       clean  - Remove cache"
	@echo ""
	@echo "💡 Examples:"
	@echo "    make dra SEAT_CONSUMERS=2          # Start with 2 seat consumers"
	@echo "    make dt test/service/ticketing/    # Test specific directory"
	@echo "    make t -k \"test_booking\"            # Test matching pattern"
	@echo ""
	@echo "📚 Full Documentation:"
	@echo "    COMMANDS.md          - Complete command reference"
	@echo "    DOCKER_QUICKSTART.md - Docker quick start guide"
	@echo "    DOCKER_GUIDE.md      - Complete Docker documentation"

.PHONY: help-full
help-full:
	@echo "Opening complete command reference..."
	@cat COMMANDS.md 2>/dev/null || echo "COMMANDS.md not found. Run 'make help' for quick reference."