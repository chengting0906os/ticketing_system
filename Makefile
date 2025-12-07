# Ticketing System - Simplified Makefile

# Load .env file if exists (- prefix ignores error if file missing)
-include .env
export

ALEMBIC_CONFIG = alembic.ini

# AWS Configuration (can be overridden via environment variables)
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")

# API Configuration (can be overridden via environment variables)
API_HOST ?= http://localhost:8100

# Deployment environment for seeding (can be overridden via environment variables)
DEPLOY_ENV ?= local_dev

# Service scaling defaults (can be overridden via .env or environment variables)
SCALE_TICKETING ?= 10
SCALE_RESERVATION ?= 10
SCALE_BOOKING ?= 10

# Default seats for seeding
SEATS ?= 500

# ==============================================================================
# 📨 KAFKA CONSUMERS
# ==============================================================================

.PHONY: c-d-build c-start c-stop c-restart rs c-tail c-status
c-d-build:  ## 🔨 Build consumer images
	@docker-compose -f docker-compose.consumers.yml build

c-start:  ## 🚀 Start all services (API + reservation-service + booking-service)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=$(SCALE_TICKETING) --scale reservation-service=$(SCALE_RESERVATION) --scale booking-service=$(SCALE_BOOKING)

c-stop:  ## 🛑 Stop consumer containers
	@docker-compose -f docker-compose.consumers.yml stop
	@docker-compose -f docker-compose.consumers.yml rm -f

c-restart:  ## 🔄 Restart consumer containers (hot reload code changes)
	@echo "🔄 Restarting consumers to reload code changes..."
	@docker-compose -f docker-compose.consumers.yml restart
	@echo "✅ Consumers restarted"

rs:  ## 🔄 Restart app services only (keep Kafka/Postgres/Kvrocks running)
	@echo "🔄 Restarting application services..."
	@echo "   📊 Ticketing: $(SCALE_TICKETING) instances"
	@echo "   📊 Reservation: $(SCALE_RESERVATION) instances"
	@echo "   📊 Booking: $(SCALE_BOOKING) instances"
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --force-recreate --scale ticketing-service=$(SCALE_TICKETING) --scale reservation-service=$(SCALE_RESERVATION) --scale booking-service=$(SCALE_BOOKING)
	@echo "✅ Application services restarted (Kafka/Postgres/Kvrocks untouched)"


# ==============================================================================
# 🗄️ DATABASE
# ==============================================================================

# Compose files for management commands
COMPOSE_FILES := -f docker-compose.yml -f docker-compose.consumers.yml

.PHONY: migrate-up migrate-down migrate-new migrate-history re-seed psql
migrate-up:  ## ⬆️ Run database migrations (in Docker)
	@docker compose $(COMPOSE_FILES) run --rm management uv run alembic -c $(ALEMBIC_CONFIG) upgrade head

migrate-down:  ## ⬇️ Rollback one migration (in Docker)
	@docker compose $(COMPOSE_FILES) run --rm management uv run alembic -c $(ALEMBIC_CONFIG) downgrade -1

migrate-new:  ## ✨ Create new migration (usage: make migrate-new MSG='message')
	@if [ -z "$(MSG)" ]; then \
		echo "Error: MSG required. Usage: make migrate-new MSG='your message'"; \
		exit 1; \
	fi
	@docker compose $(COMPOSE_FILES) run --rm management uv run alembic -c $(ALEMBIC_CONFIG) revision --autogenerate -m "$(MSG)"

migrate-history:  ## 📜 Show migration history
	@docker compose $(COMPOSE_FILES) run --rm management uv run alembic -c $(ALEMBIC_CONFIG) history

re-seed:  ## 🔄 Reset and re-seed database in Docker (default: 500 seats, usage: make re-seed SEATS=5k)
	@echo "🗑️  Resetting database..."
	@docker compose $(COMPOSE_FILES) run --rm management uv run python -m script.reset_database
	@echo "🌱 Seeding database with SEATS=$(SEATS)..."
	@docker compose $(COMPOSE_FILES) run --rm -e SEATS=$(SEATS) management uv run python -m script.seed_data
	@echo "✅ Database reset and seeded successfully"

re-seed-500:  ## 🔄 Reset and seed with 500 seats
	@$(MAKE) re-seed SEATS=500

re-seed-1k:  ## 🔄 Reset and seed with 1,000 seats
	@$(MAKE) re-seed SEATS=1k

re-seed-2k:  ## 🔄 Reset and seed with 2,000 seats
	@$(MAKE) re-seed SEATS=2k

re-seed-5k:  ## 🔄 Reset and seed with 5,000 seats
	@$(MAKE) re-seed SEATS=5k

re-seed-50k:  ## 🔄 Reset and seed with 50,000 seats
	@$(MAKE) re-seed SEATS=50k

re-seed-200k:  ## 🔄 Reset and seed with 200,000 seats
	@$(MAKE) re-seed SEATS=200k

psql:  ## 🐘 Connect to PostgreSQL
	@docker exec -it ticketing_system_db psql -U postgres -d ticketing_system_db

# ==============================================================================
# 🧪 TESTING
# ==============================================================================

.PHONY: test t-smoke t-quick t-unit t-e2e t-bdd test-cdk
# Usage: make pytest [path] or make pytest ARGS="-k test_name"
pytest:  ## 🧪 Run pytest (usage: make pytest test/path/ or make pytest ARGS="-k test_name")
	@POSTGRES_SERVER=localhost POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest --ignore=test/service/e2e -m "not cdk" -v $(ARGS) $(filter-out $@,$(MAKECMDGOALS))

t-smoke:  ## 🔥 Run smoke tests only (quick validation - integration features)
	@POSTGRES_SERVER=localhost POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest  -m "smoke" -v -n 6 --dist loadscope $(filter-out $@,$(MAKECMDGOALS))

t-quick:  ## ⚡ Run quick tests (smoke + quick tags for rapid feedback)
	@POSTGRES_SERVER=localhost POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/service/ticketing/integration/features test/service/reservation/integration/features -m "smoke or quick" -v -n 6 --dist loadscope $(filter-out $@,$(MAKECMDGOALS))

t-unit:  ## 🎯 Run unit tests only (fast, no integration/e2e)
	@POSTGRES_SERVER=localhost POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest -m unit -v $(filter-out $@,$(MAKECMDGOALS))

t-e2e:  ## 🧪 Run E2E tests
	@POSTGRES_SERVER=localhost POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

test-cdk:  ## 🏗️ Run CDK infrastructure tests (slow, CPU intensive)
	@echo "⚠️  Warning: CDK tests are CPU intensive and may take 1-2 minutes"
	@POSTGRES_SERVER=localhost POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/deployment/ -m "cdk" -v $(filter-out $@,$(MAKECMDGOALS))

%:
	@:

# ==============================================================================
# 🔧 CODE QUALITY
# ==============================================================================

.PHONY: lint format pyre clean
lint:  ## 🔍 Check code style
	@uv run ruff check .

format:  ## ✨ Format code
	@uv run ruff format .

pyre:  ## 🔬 Type checking
	@uv run pyrefly check

clean:  ## 🧹 Remove cache files
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name ".DS_Store" -delete



# ==============================================================================
# 🐳 DOCKER RESET
# ==============================================================================

.PHONY: d-reset-all dra
d-reset-all dra:  ## 🚀 Complete Docker reset (down → up → migrate → reset-kafka → seed)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo "⚠️  This will stop all containers and remove volumes"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo "🛑 Stopping everything..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml down -v
	@echo "🚀 Starting all services (API + reservation + booking)..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=$(SCALE_TICKETING) --scale reservation-service=$(SCALE_RESERVATION) --scale booking-service=$(SCALE_BOOKING)
	@echo "⏳ Waiting for services to be healthy..."
	@for i in 1 2 3 4 5 6; do \
		if docker ps --filter "name=ticketing-service" --format "{{.Status}}" | grep -q "healthy"; then \
			echo "✅ Services are healthy"; \
			break; \
		fi; \
		echo "   Attempt $$i/6: waiting 10s..."; \
		sleep 10; \
	done
	@if ! docker ps --filter "name=ticketing-service" --format "{{.Status}}" | grep -q "healthy"; then \
		echo "❌ Services failed to become healthy"; \
		exit 1; \
	fi
	@$(MAKE) d-migrate
	@$(MAKE) d-reset-kafka
	@$(MAKE) d-seed
	@echo ""
	@echo "✅ ==================== SETUP COMPLETE ===================="
	@echo "   🌐 API:  http://localhost:8100/docs#"
	@echo "   📊 Kafka UI:     http://localhost:8080"
	@echo "   📈 Grafana:      http://localhost:3000"
	@echo "   🔍 Jaeger:       http://localhost:16686"
	@echo ""

.PHONY: d-migrate d-seed d-reset-kafka tdt
d-migrate:  ## 🗄️ Run migrations in Docker
	@echo "🗄️  Running database migrations..."
	@docker-compose exec ticketing-service uv run alembic upgrade head
	@echo "✅ Migrations completed"

d-seed:  ## 🌱 Seed data in Docker
	@docker-compose exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/seed_data.py"

d-reset-kafka:  ## 🌊 Reset Kafka in Docker
	@echo "🌊 Resetting Kafka..."
	@docker-compose exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/reset_kafka.py"
	@echo "✅ Kafka reset completed"

tdt:  ## 🧪 Run tests in Docker (excludes E2E, deployment, SSE slow tests)
	@docker-compose exec ticketing-service uv run pytest test/ \
		-n 4\
		--ignore=test/service/e2e \
		--ignore=test/deployment \
		--ignore=test/service/reservation/integration/features/seat_status_sse_stream.feature \
		-v





# ==============================================================================
# 🎯 K6 LOAD TESTING
# ==============================================================================

.PHONY: k6-dev-load k6-dev-stress k6-dev-spike k6-prod-load k6-prod-stress k6-prod-spike
k6-dev-load:  ## 🎯 Run k6 load test (dev: ~10K req, peak 900 RPS)
	@k6 run script/k6/dev/load-test.js

k6-dev-stress:  ## 💥 Run k6 stress test (dev: peak 1000 RPS)
	@k6 run script/k6/dev/stress-test.js

k6-dev-spike:  ## ⚡ Run k6 spike test (dev: spike to 1000 RPS)
	@k6 run script/k6/dev/spike-test.js

k6-prod-load:  ## 🚀 Run k6 load test (prod: ~20K req, peak 1800 RPS)
	@k6 run -e API_HOST=$(API_HOST) script/k6/production/load-test.js

k6-prod-stress:  ## 💥 Run k6 stress test (prod: peak 7000 RPS)
	@k6 run -e API_HOST=$(API_HOST) script/k6/production/stress-test.js

k6-prod-spike:  ## ⚡ Run k6 spike test (prod: spike to 5000 RPS)
	@k6 run -e API_HOST=$(API_HOST) script/k6/production/spike-test.js

# ==============================================================================
# ⚡ LOAD TESTING (Auto-forwarded to script/go_client/Makefile)
# ==============================================================================
# Usage: make go-<target>
#   make go-clt-t/s/m/l/f      # Concurrent load test (tiny → full)
#   make go-frlt-{500,5k,50k,200k}  # Full reserved load test (default: 500)
#   make go-help               # Show all go_client commands
# ==============================================================================

# Auto-delegate all go-* targets to script/go_client/Makefile
go-%:
	@$(MAKE) -C script/go_client $(subst go-,,$@)


# ==============================================================================
# ☁️ AWS OPERATIONS (deployment/Makefile)
# ==============================================================================
# Run with: make -f deployment/Makefile <target> or make aws-<target>
#   aws-start/stop/status     - Service lifecycle
#   aws-lt-exec               - Connect to LoadTest EC2
#   dev-deploy-full           - Build + Push + Deploy
# ==============================================================================

# Auto-delegate all aws-* targets to deployment/Makefile
aws-%:
	@$(MAKE) -f deployment/Makefile $@

# Auto-delegate CDK targets to deployment/Makefile
cdk-%:
	@$(MAKE) -f deployment/Makefile $@

# Auto-delegate ECR targets to deployment/Makefile
ecr-%:
	@$(MAKE) -f deployment/Makefile $@

# Auto-delegate deployment targets to deployment/Makefile
.PHONY: deploy destroy dev-deploy-full dev-deploy-all prod-deploy-full prod-deploy-all
deploy destroy dev-deploy-full dev-deploy-all prod-deploy-full prod-deploy-all:
	@$(MAKE) -f deployment/Makefile $@

# ==============================================================================
# 📖 HELP
# ==============================================================================

.PHONY: help
help:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           📋 Ticketing System - Makefile Commands            ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "🚀 QUICK START"
	@echo "  d-reset-all (dra)  - Complete Docker reset (down → up → migrate → seed)"
	@echo "  reset              - Quick reset (Kafka + Kvrocks + DB, no restart)"
	@echo ""
	@echo "🐳 DOCKER"
	@echo "  c-start / c-stop / c-restart  - Service lifecycle"
	@echo "  rs                            - Restart all services with scaling"
	@echo "  c-d-build                     - Build images"
	@echo "  d-migrate / d-seed / d-reset-kafka"
	@echo ""
	@echo "🗄️  DATABASE"
	@echo "  migrate-up / down / new / history"
	@echo "  re-seed-{500,1k,2k,5k,50k,200k} - Seed with different sizes"
	@echo "  psql                        - Connect to PostgreSQL"
	@echo ""
	@echo "🧪 TESTING"
	@echo "  pytest      - Run all tests"
	@echo "  t-smoke / t-quick / t-unit / t-e2e"
	@echo "  tdt         - Run tests in Docker"
	@echo ""
	@echo "🔧 CODE QUALITY"
	@echo "  format / lint / pyre / clean"
	@echo ""
	@echo "⚡ LOAD TESTING"
	@echo "  go-clt-t/s/m/l/f  - Concurrent load test (tiny → full)"
	@echo "  go-frlt-{500,5k,50k,200k} - Full reserved load test"
	@echo "  k6-dev-load / k6-dev-stress / k6-dev-spike / k6-prod-load / k6-prod-stress / k6-prod-spike"
	@echo ""
	@echo "☁️  AWS (make -f deployment/Makefile help)"
	@echo "  dev-deploy-full / prod-deploy-full"
	@echo ""
	@echo "📖 DOCS: spec/CONSTITUTION.md"
