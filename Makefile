# Ticketing System - Simplified Makefile
ALEMBIC_CONFIG = alembic.ini

# AWS Configuration (can be overridden via environment variables)
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")

# API Configuration (can be overridden via environment variables)
API_HOST ?= http://localhost:8100

# Deployment environment for seeding (can be overridden via environment variables)
DEPLOY_ENV ?= local_dev

# ==============================================================================
# 📨 KAFKA CONSUMERS
# ==============================================================================

.PHONY: c-d-build c-start c-stop c-restart c-tail c-status
c-d-build:  ## 🔨 Build consumer images
	@docker-compose -f docker-compose.consumers.yml build

c-start:  ## 🚀 Start all services (API + reservation-service + booking-service)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=2 --scale reservation-service=4 --scale booking-service=2

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

re-seed:  ## 🔄 Reset and re-seed database (usage: make re-seed DEPLOY_ENV=local_dev_1000)
	@echo "🗑️  Resetting database..."
	@POSTGRES_SERVER=localhost KVROCKS_HOST=localhost uv run python -m script.reset_database
	@echo "🌱 Seeding database with DEPLOY_ENV=$(DEPLOY_ENV)..."
	@POSTGRES_SERVER=localhost KVROCKS_HOST=localhost DEPLOY_ENV=$(DEPLOY_ENV) uv run python -m script.seed_data
	@echo "✅ Database reset and seeded successfully"

re-seed-1k:  ## 🔄 Reset and seed with 1000 seats (local_dev_1000)
	@$(MAKE) re-seed DEPLOY_ENV=local_dev_1000

re-seed-5k:  ## 🔄 Reset and seed with 5000 seats (staging)
	@$(MAKE) re-seed DEPLOY_ENV=staging

re-seed-2k:  ## 🔄 Reset and seed with 2000 seats (local_dev_2k)
	@$(MAKE) re-seed DEPLOY_ENV=local_dev_2k

re-seed-50k:  ## 🔄 Reset and seed with 50000 seats (production)
	@$(MAKE) re-seed DEPLOY_ENV=production

psql:  ## 🐘 Connect to PostgreSQL
	@docker exec -it ticketing_system_db psql -U py_arch_lab -d ticketing_system_db

# ==============================================================================
# 🧪 TESTING
# ==============================================================================

.PHONY: test t-smoke t-quick t-unit t-e2e t-bdd test-cdk
pytest:  ## 🧪 Run unit tests (excludes CDK and E2E)
	@POSTGRES_SERVER=localhost POSTGRES_USER=py_arch_lab POSTGRES_PASSWORD=py_arch_lab POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/ --ignore=test/service/e2e -m "not cdk" -v $(filter-out $@,$(MAKECMDGOALS))

t-smoke:  ## 🔥 Run smoke tests only (quick validation - integration features)
	@POSTGRES_SERVER=localhost POSTGRES_USER=py_arch_lab POSTGRES_PASSWORD=py_arch_lab POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest  -m "smoke" -v -n 6 --dist loadscope $(filter-out $@,$(MAKECMDGOALS))

t-quick:  ## ⚡ Run quick tests (smoke + quick tags for rapid feedback)
	@POSTGRES_SERVER=localhost POSTGRES_USER=py_arch_lab POSTGRES_PASSWORD=py_arch_lab POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/service/ticketing/integration/features test/service/seat_reservation/integration/features -m "smoke or quick" -v -n 6 --dist loadscope $(filter-out $@,$(MAKECMDGOALS))

t-unit:  ## 🎯 Run unit tests only (fast, no integration/e2e)
	@POSTGRES_SERVER=localhost POSTGRES_USER=py_arch_lab POSTGRES_PASSWORD=py_arch_lab POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest -m unit -v $(filter-out $@,$(MAKECMDGOALS))

t-e2e:  ## 🧪 Run E2E tests
	@POSTGRES_SERVER=localhost POSTGRES_USER=py_arch_lab POSTGRES_PASSWORD=py_arch_lab POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

test-cdk:  ## 🏗️ Run CDK infrastructure tests (slow, CPU intensive)
	@echo "⚠️  Warning: CDK tests are CPU intensive and may take 1-2 minutes"
	@POSTGRES_SERVER=localhost POSTGRES_USER=py_arch_lab POSTGRES_PASSWORD=py_arch_lab POSTGRES_PORT=5432 KVROCKS_HOST=localhost KVROCKS_PORT=6666 KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9093,localhost:9094 uv run pytest test/deployment/ -m "cdk" -v $(filter-out $@,$(MAKECMDGOALS))

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

.PHONY: scale-up scale-down scale-ticketing scale-reservation scale-booking scale-status dra
scale-up:  ## 🚀 Scale services (usage: make scale-up A=2 R=4 B=2)
	@if [ -z "$(A)" ] || [ -z "$(R)" ] || [ -z "$(B)" ]; then \
		echo "Usage: make scale-up A=<api_count> R=<reservation_count> B=<booking_count>"; \
		echo "Example: make scale-up A=2 R=4 B=2"; \
		exit 1; \
	fi
	@echo "📈 Scaling services: API=$(A), reservation=$(R), booking=$(B)"
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=$(A) --scale reservation-service=$(R) --scale booking-service=$(B) --no-recreate
	@echo "✅ Scaled successfully!"
	@docker-compose ps ticketing-service reservation-service booking-service

scale-down:  ## 📉 Scale down to 1 instance each
	@echo "📉 Scaling down to 1 instance each..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=1 --scale reservation-service=1 --scale booking-service=1 --no-recreate
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
	@docker-compose -f docker-compose.consumers.yml up -d --scale reservation-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose ps reservation-service

scale-booking:  ## 📝 Scale only booking service (usage: make scale-booking N=2)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-booking N=<count>"; \
		echo "Example: make scale-booking N=2"; \
		exit 1; \
	fi
	@echo "📈 Scaling booking-service to $(N) instances..."
	@docker-compose -f docker-compose.consumers.yml up -d --scale booking-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose ps booking-service

scale-status:  ## 📊 Show current scaling status
	@echo "📊 Current service instances:"
	@docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | grep -E "(ticketing-service|reservation-service|booking-service|nginx)"

dra:  ## 🚀 Complete Docker reset (down → up → migrate → reset-kafka → seed)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo "⚠️  This will stop all containers and remove volumes"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo "🛑 Stopping everything..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml down -v
	@echo "🚀 Starting all services (API + reservation + booking)..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=10 --scale reservation-service=10 --scale booking-service=10
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
	@echo "   🌐 API :  http://localhost:8100/docs#
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

tdt:  ## 🧪 Run tests in Docker (excludes E2E, deployment, SSE slow tests)
	@docker-compose exec ticketing-service uv run pytest test/ \
		-n 4\
		--ignore=test/service/e2e \
		--ignore=test/deployment \
		--ignore=test/service/seat_reservation/integration/features/seat_status_sse_stream.feature \
		-v





# ==============================================================================
# 🎯 K6 LOAD TESTING
# ==============================================================================

.PHONY: k6-local k6-stress k6-prod k6-prod-stress
k6-local:  ## 🎯 Run k6 load test (local: peak 250 RPS, 1 min)
	@k6 run script/k6/local/load-test.js

k6-stress:  ## 💥 Run k6 stress test (local: peak 500 RPS)
	@k6 run script/k6/local/stress-test.js

k6-prod:  ## 🚀 Run k6 load test (production: peak 2500 RPS)
	@k6 run -e API_URL=$(API_HOST) script/k6/production/load-test.js

k6-prod-stress:  ## 💥 Run k6 stress test (production: peak 7000 RPS)
	@k6 run -e API_URL=$(API_HOST) script/k6/production/stress-test.js

# ==============================================================================
# ⚡ LOAD TESTING (Auto-forwarded to script/go_client/Makefile)
# ==============================================================================
# All go-* targets are forwarded to script/go_client/Makefile
# Usage: make go-<target>
#   make go-clt-t          # Tiny concurrent load test
#   make go-clt-s          # Small concurrent load test
#   make go-clt-m          # Medium concurrent load test
#   make go-clt-l          # Large concurrent load test
#   make go-clt-f          # Full concurrent load test
#   make go-rlt            # Reserved load test (auto-detect env)
#   make go-rlt-1k         # Reserved load test (1000 seats)
#   make go-frlt           # Full reserved load test (WORKERS=100 BATCH=1)
#   make go-frlt-1k        # Full reserved load test (1000 seats)
#   make go-frlt-staging   # Full reserved load test (5000 seats)
#   make go-frlt-prod      # Full reserved load test (50000 seats)
#   make go-both-m         # Both tests in parallel - medium
#   make go-both-l         # Both tests in parallel - large
#   make go-both-f         # Both tests in parallel - full
#   make go-help           # Show go_client Makefile help
#
# For full list: cd script/go_client && make help
# ==============================================================================

# Auto-delegate all go-* targets to script/go_client/Makefile
go-%:
	@$(MAKE) -C script/go_client $(subst go-,,$@)


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
	@echo "  c-start     - Start all services (API + reservation + booking)"
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
	@echo "  re-seed     - Reset and re-seed database (usage: DEPLOY_ENV=local_dev_1000 make re-seed)"
	@echo "  re-seed-1k  - Reset and seed with 1000 seats"
	@echo "  re-seed-2k  - Reset and seed with 2000 seats"
	@echo "  re-seed-staging - Reset and seed with 5000 seats"
	@echo "  re-seed-prod - Reset and seed with 50000 seats"
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
	@echo "  scale-up    - Scale services (usage: make scale-up A=2 R=4 B=2)"
	@echo "  scale-down  - Scale down to 1 instance each"
	@echo "  scale-ticketing - Scale API service (usage: make scale-ticketing N=3)"
	@echo "  scale-reservation - Scale reservation-service (usage: make scale-reservation N=2)"
	@echo "  scale-booking - Scale booking-service (usage: make scale-booking N=2)"
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
	@echo "  go-rlt-1k   - Reserved Load Test - 1,000 seats (local_dev_1000)"
	@echo "  go-frlt     - Full Reserved Load Test - Configurable (WORKERS=100 BATCH=1)"
	@echo "  go-frlt-1k  - Full Reserved Load Test - 1,000 seats"
	@echo "  go-frlt-2k  - Full Reserved Load Test - 2,000 seats"
	@echo "  go-frlt-5k  - Full Reserved Load Test - 5,000 seats (staging)"
	@echo "  go-frlt-50k - Full Reserved Load Test - 50,000 seats (production)"
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
	@echo "  make re-seed-1k                         # Seed 1000 seats"
	@echo "  DEPLOY_ENV=staging make re-seed         # Seed 5000 seats"
	@echo "  make test test/service/ticketing/       # Test specific directory"
	@echo "  make migrate-new MSG='add user table'   # Create migration"
	@echo "  make scale-ticketing N=5                # Scale to 5 API instances"
	@echo "  make go-rlt                             # Run sellout load test"
	@echo ""
	@echo "📚 ARCHITECTURE NOTES"
	@echo "  • ticketing-service: API service with Redis Pub/Sub for real-time cache"
	@echo "  • reservation-service: Standalone consumer for seat reservations"
	@echo "  • booking-service: Standalone consumer for booking creation"
	@echo "  • Nginx load balancer simulates AWS ALB locally"
	@echo ""
	@echo "📖 DOCS: spec/CONSTITUTION.md | spec/TICKETING_SERVICE_SPEC.md | spec/SEAT_RESERVATION_SPEC.md"
