# Ticketing System - Simplified Makefile
ALEMBIC_CONFIG = alembic.ini

# AWS Configuration (can be overridden via environment variables)
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")

# API Configuration (can be overridden via environment variables)
API_HOST ?= http://localhost:8100

# ==============================================================================
# 📨 KAFKA CONSUMERS
# ==============================================================================

.PHONY: c-d-build c-start c-stop c-restart c-tail c-status
c-d-build:  ## 🔨 Build consumer images
	@docker-compose -f docker-compose.consumers.yml build

c-start:  ## 🚀 Start all services (API=1, booking=4, reservation=4)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=2 --scale booking-service=2 --scale reservation-service=2

c-stop:  ## 🛑 Stop consumer containers
	@docker-compose -f docker-compose.consumers.yml stop
	@docker-compose -f docker-compose.consumers.yml rm -f

c-restart:  ## 🔄 Restart consumer containers (hot reload code changes)
	@echo "🔄 Restarting consumers to reload code changes..."
	@docker-compose -f docker-compose.consumers.yml restart
	@echo "✅ Consumers restarted"

c-tail:  ## 📝 Tail consumer logs
	@docker-compose -f docker-compose.consumers.yml logs -f

c-status:  ## 📊 Consumer status
	@docker-compose -f docker-compose.consumers.yml ps

# ==============================================================================
# 🗄️ DATABASE
# ==============================================================================

.PHONY: migrate-up migrate-down migrate-new migrate-history re-seed psql
migrate-up:  ## ⬆️ Run database migrations
	@uv run alembic -c $(ALEMBIC_CONFIG) upgrade head

migrate-down:  ## ⬇️ Rollback one migration
	@uv run alembic -c $(ALEMBIC_CONFIG) downgrade -1

migrate-new:  ## ✨ Create new migration (usage: make migrate-new MSG='message')
	@if [ -z "$(MSG)" ]; then \
		echo "Error: MSG required. Usage: make migrate-new MSG='your message'"; \
		exit 1; \
	fi
	@uv run alembic -c $(ALEMBIC_CONFIG) revision --autogenerate -m "$(MSG)"

migrate-history:  ## 📜 Show migration history
	@uv run alembic -c $(ALEMBIC_CONFIG) history

re-seed:  ## 🔄 Reset and re-seed database
	@echo "🗑️  Resetting database..."
	@uv run python -m script.reset_database
	@echo "🌱 Seeding database..."
	@uv run python -m script.seed_data
	@echo "✅ Database reset and seeded successfully"

psql:  ## 🐘 Connect to PostgreSQL
	@docker exec -it ticketing_system_db psql -U py_arch_lab -d ticketing_system_db

# ==============================================================================
# 🧪 TESTING
# ==============================================================================

.PHONY: test t-smoke t-quick t-unit t-e2e t-bdd test-cdk
test:  ## 🧪 Run unit tests (excludes CDK and E2E)
	@uv run pytest test/ --ignore=test/service/e2e -m "not cdk" -v $(filter-out $@,$(MAKECMDGOALS))

t-smoke:  ## 🔥 Run smoke tests only (quick validation - integration features)
	@uv run pytest  -m "smoke" -v -n 6 $(filter-out $@,$(MAKECMDGOALS))

t-quick:  ## ⚡ Run quick tests (smoke + quick tags for rapid feedback)
	@uv run pytest test/service/ticketing/integration/features test/service/seat_reservation/integration/features -m "smoke or quick" -v -n 6 $(filter-out $@,$(MAKECMDGOALS))

t-unit:  ## 🎯 Run unit tests only (fast, no integration/e2e)
	@uv run pytest -m unit -v -n 6 $(filter-out $@,$(MAKECMDGOALS))

t-e2e:  ## 🧪 Run E2E tests
	@uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

test-cdk:  ## 🏗️ Run CDK infrastructure tests (slow, CPU intensive)
	@echo "⚠️  Warning: CDK tests are CPU intensive and may take 1-2 minutes"
	@uv run pytest test/deployment/ -m "cdk" -v $(filter-out $@,$(MAKECMDGOALS))

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
# 🔄 QUICK RESET (Local Development)
# ==============================================================================

.PHONY: reset
reset:  ## 🔄 Quick reset (clean DB + Kafka + Kvrocks + seed, no container restart)
	@echo "🔄 ==================== QUICK RESET ===================="
	@echo "📋 This will:"
	@echo "   1. Clean Kafka + Kvrocks + RocksDB"
	@echo "   2. Run database migrations"
	@echo "   3. Seed initial data"
	@echo ""
	@echo "⚠️  Containers will stay running (faster than 'make dra')"
	@echo ""
	@$(MAKE) ka
	@echo ""
	@$(MAKE) dm
	@echo ""
	@$(MAKE) ds
	@echo ""
	@echo "✅ ==================== RESET COMPLETE ===================="
	@echo "💡 Full restart needed? Use 'make dra' instead"
	@echo ""

# ==============================================================================
# 🐳 DOCKER - PRIMARY WORKFLOW
# ==============================================================================

.PHONY: d-s-rs s-d-build

d-s-rs:  ## 🔄 Restart services
	@docker-compose restart ticketing-service

s-d-build:  ## 🔨 Rebuild services
	@docker-compose build ticketing-service

# ==============================================================================
# 📈 SERVICE SCALING (Nginx Load Balancer)
# ==============================================================================

.PHONY: scale-up scale-down scale-ticketing scale-reservation scale-status dra
scale-up:  ## 🚀 Scale services (usage: make scale-up T=3 R=2)
	@if [ -z "$(T)" ] || [ -z "$(R)" ]; then \
		echo "Usage: make scale-up T=<ticketing_count> R=<reservation_count>"; \
		echo "Example: make scale-up T=3 R=2"; \
		exit 1; \
	fi
	@echo "📈 Scaling services: ticketing=$(T), reservation=$(R)"
	@docker-compose up -d --scale ticketing-service=$(T) --scale reservation-service=$(R) --no-recreate
	@echo "✅ Scaled successfully!"
	@docker-compose ps ticketing-service reservation-service

scale-down:  ## 📉 Scale down to 1 instance each
	@echo "📉 Scaling down to 1 instance each..."
	@docker-compose up -d --scale ticketing-service=1 --scale reservation-service=1 --no-recreate
	@echo "✅ Scaled down successfully!"

scale-ticketing:  ## 🎫 Scale only ticketing service (usage: make scale-ticketing N=3)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-ticketing N=<count>"; \
		echo "Example: make scale-ticketing N=5"; \
		exit 1; \
	fi
	@echo "📈 Scaling ticketing-service to $(N) instances..."
	@docker-compose up -d --scale ticketing-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose ps ticketing-service

scale-reservation:  ## 🪑 Scale only reservation service (usage: make scale-reservation N=2)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-reservation N=<count>"; \
		echo "Example: make scale-reservation N=3"; \
		exit 1; \
	fi
	@echo "📈 Scaling reservation-service to $(N) instances..."
	@docker-compose up -d --scale reservation-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose ps reservation-service

scale-status:  ## 📊 Show current scaling status
	@echo "📊 Current service instances:"
	@docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | grep -E "(ticketing-service|reservation-service|nginx)"

dra:  ## 🚀 Complete Docker reset (down → up → migrate → reset-kafka → seed)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo "⚠️  This will stop all containers and remove volumes"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo "🛑 Stopping everything..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml down -v
	@echo "🚀 Starting all services (API=1, booking=4, reservation=4)..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=2 --scale booking-service=10 --scale reservation-service=10
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
	@$(MAKE) dm
	@$(MAKE) drk
	@$(MAKE) ds
	@echo ""
	@echo "✅ ==================== SETUP COMPLETE ===================="
	@echo "   🌐 API (Nginx):  $(API_HOST)/docs"
	@echo "   📊 Kafka UI:     http://localhost:8080"
	@echo "   📈 Grafana:      http://localhost:3000"
	@echo "   🔍 Jaeger:       http://localhost:16686"
	@echo ""

.PHONY: dm ds drk tdt tdinfra tdci
dm:  ## 🗄️ Run migrations in Docker
	@echo "🗄️  Running database migrations..."
	@docker-compose exec ticketing-service uv run alembic upgrade head
	@echo "✅ Migrations completed"

ds:  ## 🌱 Seed data in Docker
	@docker-compose exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/seed_data.py"

drk:  ## 🌊 Reset Kafka in Docker
	@echo "🌊 Resetting Kafka..."
	@docker-compose exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/reset_kafka.py"
	@echo "✅ Kafka reset completed"

tdt:  ## 🧪 Run tests in Docker (excludes E2E, deployment, infra, skipped features)
	@docker-compose exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/deployment \
		--ignore=test/infrastructure \
		--ignore=test/service/ticketing/integration/features/booking_insufficient_seats.feature \
		-v

tdinfra:  ## 🏗️ Run infrastructure tests in Docker
	@echo "🏗️  Testing infrastructure components in Docker..."
	@docker-compose exec ticketing-service uv run pytest test/infrastructure/ -v --tb=short
	@echo "✅ Infrastructure tests complete!"

tdci:  ## 🤖 Run CI tests (exclude infra, api, e2e, deployment)
	@docker-compose exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/infrastructure \
		--ignore=test/deployment \
		-m "not api and not infra and not e2e" \
		-v

# ==============================================================================
# ⚡ LOAD TESTING
# ==============================================================================

# Build Targets
.PHONY: go-build-concurrent go-build-reserved go-build-full-reserved g-b-c g-b-r g-b-f

go-build-concurrent g-b-c:  ## 🔨 Build Go concurrent load test binary
	@cd script/go_client && go build -tags concurrent -o concurrent_loadtest

go-build-reserved g-b-r:  ## 🔨 Build Go reserved load test binary
	@cd script/go_client && go build -tags reserved -o reserved_loadtest

go-build-full-reserved g-b-f:  ## 🔨 Build Go full reserved load test binary (500 workers, 1 ticket each)
	@cd script/go_client && go build -tags full_reserved -o full_reserved_loadtest



# Concurrent Load Test (Pressure Testing)
.PHONY: go-clt-t go-clt-s go-clt-m go-clt-l go-clt-f

go-clt-t: go-build-concurrent  ## 🧪 Concurrent Load Test - Tiny (10 requests, 5 concurrency, 5 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 10 -concurrency 5 -clients 5

go-clt-s: go-build-concurrent  ## 🧪 Concurrent Load Test - Small (100 requests, 10 concurrency, 10 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 100 -concurrency 10 -clients 10

go-clt-m: go-build-concurrent  ## ⚡ Concurrent Load Test - Medium (5000 requests, 50concurrency, 50 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 500 -concurrency 25 -clients 25

go-clt-l: go-build-concurrent  ## ⚡ Concurrent Load Test - Large (10000 requests, 50 concurrency, 50 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 15000 -concurrency 50 -clients 50

go-clt-f: go-build-concurrent  ## 💪 Concurrent Load Test - Full (50000 requests, 100 concurrency, 100 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 150000 -concurrency 100 -clients 100


# Reserved Load Test (Sellout Testing)
.PHONY: go-rlt go-frlt

go-rlt: go-build-reserved  ## 🔥 Reserved Load Test - Buys all seats (random 1-4 tickets, 100 workers)
	@echo "🔥 Running reserved load test (Go)..."
	@if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "📊 Production mode: 50,000 seats"; \
		cd script/go_client && ./reserved_loadtest -env production -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "📊 Staging mode: 5,000 seats"; \
		cd script/go_client && ./reserved_loadtest -env staging -event 1 -workers 100 -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "📊 Local Dev 1000 mode: 1,000 seats"; \
		cd script/go_client && ./reserved_loadtest -env local_dev_1000 -event 1 -workers 100 -host $(API_HOST); \
	else \
		echo "📊 Development mode: 500 seats"; \
		cd script/go_client && ./reserved_loadtest -env development -event 1 -workers 100 -host $(API_HOST); \
	fi

go-frlt: go-build-full-reserved  ## 🚀 Full Reserved Load Test - Configurable (WORKERS=100 BATCH=1 make go-frlt)
	@WORKERS=$${WORKERS:-100}; \
	BATCH=$${BATCH:-1}; \
	echo "🚀 Running FULL reserved load test (Workers: $$WORKERS, Batch: $$BATCH)..."; \
	if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "📊 Production mode: 50,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env production -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "📊 Staging mode: 5,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env staging -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "📊 Local Dev 1000 mode: 1,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env local_dev_1000 -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	else \
		echo "📊 Development mode: 500 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env development -event 1 -workers $$WORKERS -batch $$BATCH -host $(API_HOST); \
	fi

# Combined Load Tests (Concurrent + Reserved) - Run in PARALLEL
.PHONY: go-both-m go-both-l go-both-f

go-both-m: go-build-concurrent go-build-reserved  ## 🔄 Both Tests PARALLEL - Medium (CLT: 500/25 + RLT: 20)
	@echo "🔄 Running BOTH tests in PARALLEL - Medium"
	@cd script/go_client && \
		./reserved_loadtest -env development -event 1 -workers 100 & \
		./concurrent_loadtest -requests 500 -concurrency 25 -clients 25 & \
		wait

go-both-l: go-build-concurrent go-build-reserved  ## 🔄 Both Tests PARALLEL - Large (CLT: 5000/50 + RLT: 50)
	@echo "🔄 Running BOTH tests in PARALLEL - Large"
	@cd script/go_client && \
		./concurrent_loadtest -requests 5000 -concurrency 50 -clients 50 & \
		./reserved_loadtest -env staging -event 1 -workers 50 & \
		wait

go-both-f: go-build-concurrent go-build-reserved  ## 🔄 Both Tests PARALLEL - Full (CLT: 50000/100 + RLT: 100)
	@echo "🔄 Running BOTH tests in PARALLEL - Full"
	@cd script/go_client && \
		./concurrent_loadtest -requests 50000 -concurrency 100 -clients 100 & \
		./reserved_loadtest -env production -event 1 -workers 100 & \
		wait


# ==============================================================================
# ☁️ AWS OPERATIONS
# ==============================================================================
# All AWS-related commands are now in deployment/Makefile
# Run them with: make -f deployment/Makefile <target>
# Or use: make aws-<command> (auto-delegated)
#
# Available AWS commands:
#   aws-go-clt-t/s/m/l/f      - AWS Load Testing
#   aws-go-rlt                - AWS Reserved Load Test
#   aws-loadtest-full         - Complete workflow (seed + loadtest)
#   aws-loadtest-run/exec     - Interactive LoadTest task
#   dev-deploy-all/full       - Deploy to development
#   prod-deploy-all/full      - Deploy to production
#   aws-reset                 - Complete reset (migrate + seed)
#   aws-status/logs           - Service monitoring
#
# For full list: make -f deployment/Makefile help
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
	@echo "  reset       - Quick reset (Kafka + Kvrocks + DB + seed, no restart)"
	@echo "  dra         - Complete Docker reset (down → up → migrate → seed)"
	@echo ""
	@echo "📨 SERVICES"
	@echo "  c-d-build   - Build service images"
	@echo "  c-start     - Start all services (ticketing=2, reservation=4)"
	@echo "  c-stop      - Stop consumer containers"
	@echo "  c-restart   - Restart consumers (hot reload)"
	@echo "  c-tail      - Tail consumer logs"
	@echo "  c-status    - Show consumer status"
	@echo ""
	@echo "🗄️  DATABASE"
	@echo "  migrate-up  - Run migrations"
	@echo "  migrate-down - Rollback one migration"
	@echo "  migrate-new - Create new migration (usage: make migrate-new MSG='message')"
	@echo "  migrate-history - Show migration history"
	@echo "  re-seed     - Reset and re-seed database"
	@echo "  psql        - Connect to PostgreSQL"
	@echo "  dm          - Run migrations in Docker"
	@echo "  ds          - Seed data in Docker (500/5K/50K seats)"
	@echo "  drk         - Reset Kafka in Docker"
	@echo ""
	@echo "🧪 TESTING"
	@echo "  test        - Run unit tests (excludes CDK and E2E)"
	@echo "  t-smoke     - Run smoke tests only (integration features)"
	@echo "  t-quick     - Run quick tests (smoke + quick tags)"
	@echo "  t-unit      - Run unit tests only"
	@echo "  t-e2e       - Run E2E tests"
	@echo "  test-cdk    - Run CDK infrastructure tests"
	@echo "  tdt         - Run tests in Docker"
	@echo "  tdinfra     - Run infrastructure tests in Docker"
	@echo "  tdci        - Run CI tests in Docker"
	@echo ""
	@echo "🔧 CODE QUALITY"
	@echo "  format      - Format code with ruff"
	@echo "  lint        - Check code style"
	@echo "  pyre        - Type checking"
	@echo "  clean       - Remove cache files"
	@echo ""
	@echo "📈 SERVICE SCALING (Nginx Load Balancer)"
	@echo "  scale-up    - Scale services (usage: make scale-up T=3 R=2)"
	@echo "  scale-down  - Scale down to 1 instance each"
	@echo "  scale-ticketing - Scale ticketing-service (usage: make scale-ticketing N=3)"
	@echo "  scale-reservation - Scale reservation-service (usage: make scale-reservation N=2)"
	@echo "  scale-booking     - Scale booking-service (usage: make scale-booking N=2)"
	@echo "  scale-status - Show current scaling status"
	@echo "  d-s-rs      - Restart ticketing-service"
	@echo "  s-d-build   - Rebuild ticketing-service"
	@echo ""
	@echo "⚡ LOAD TESTING (Go Clients)"
	@echo "  go-clt-t    - Concurrent Load Test - Tiny (10 req, 5 concurrency)"
	@echo "  go-clt-s    - Concurrent Load Test - Small (100 req, 10 concurrency)"
	@echo "  go-clt-m    - Concurrent Load Test - Medium (5K req, 25 concurrency)"
	@echo "  go-clt-l    - Concurrent Load Test - Large (10K req, 50 concurrency)"
	@echo "  go-clt-f    - Concurrent Load Test - Full (50K req, 100 concurrency)"
	@echo "  go-rlt      - Reserved Load Test - Buys all seats (DEPLOY_ENV: local_dev/development/production)"
	@echo ""
	@echo "☁️  AWS OPERATIONS (delegated to deployment/Makefile)"
	@echo "  dev-deploy-full  - Build + Push + Deploy to development"
	@echo "  dev-deploy-all   - Deploy CDK stacks only (images must exist)"
	@echo "  prod-deploy-full - Build + Push + Deploy to production"
	@echo "  prod-deploy-all  - Deploy to production (images must exist)"
	@echo "  aws-*       - AWS ECS operations (aws-restart, aws-status, etc.)"
	@echo "  cdk-*       - CDK operations (cdk-synth, cdk-diff, etc.)"
	@echo "  ecr-*       - ECR operations"
	@echo "  For full list: make -f deployment/Makefile help"
	@echo ""
	@echo "💡 EXAMPLES"
	@echo "  make dra                                # Fresh start with Docker"
	@echo "  make reset                              # Quick reset (no restart)"
	@echo "  make test test/service/ticketing/       # Test specific directory"
	@echo "  make migrate-new MSG='add user table'   # Create migration"
	@echo "  make scale-ticketing N=5                # Scale to 5 API instances"
	@echo "  make go-rlt                             # Run sellout load test"
	@echo ""
	@echo "📚 ARCHITECTURE NOTES"
	@echo "  • Consumers run as standalone services (docker-compose.consumers.yml)"
	@echo "  • booking-service: Processes booking events from Kafka"
	@echo "  • reservation-service: Processes seat reservation events from Kafka"
	@echo "  • Nginx load balancer simulates AWS ALB locally"
	@echo ""
	@echo "📖 DOCS: spec/CONSTITUTION.md | spec/TICKETING_SERVICE_SPEC.md | spec/SEAT_RESERVATION_SPEC.md"
