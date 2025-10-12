# Ticketing System - Simplified Makefile
ALEMBIC_CONFIG = alembic.ini

# ==============================================================================
# 🚀 QUICK START
# ==============================================================================

.PHONY: reset reset-all
reset:  ## 🔄 Reset Kafka + Database + Seed data
	@echo "🚀 Complete system reset..."
	@PYTHONPATH=. uv run python script/reset_kafka.py
	@PYTHONPATH=. uv run python script/reset_database.py
	@PYTHONPATH=. uv run python script/seed_data.py
	@echo "✅ Reset complete!"

reset-all: reset  ## 🔄 Reset + start services (DEPRECATED: use Docker)
	@echo "⚠️  Local services deprecated. Use 'make dra' for Docker"

# ==============================================================================
# 🗄️ DATABASE
# ==============================================================================

.PHONY: migrate-up
migrate-up:  ## ⬆️ Run database migrations
	@uv run alembic -c $(ALEMBIC_CONFIG) upgrade head

.PHONY: migrate-down
migrate-down:  ## ⬇️ Rollback one migration
	@uv run alembic -c $(ALEMBIC_CONFIG) downgrade -1

.PHONY: migrate-new
migrate-new:  ## ✨ Create new migration (usage: make migrate-new MSG='message')
	@if [ -z "$(MSG)" ]; then \
		echo "Error: MSG required. Usage: make migrate-new MSG='your message'"; \
		exit 1; \
	fi
	@uv run alembic -c $(ALEMBIC_CONFIG) revision --autogenerate -m "$(MSG)"

.PHONY: migrate-history
migrate-history:  ## 📜 Show migration history
	@uv run alembic -c $(ALEMBIC_CONFIG) history

.PHONY: psql
psql:  ## 🐘 Connect to PostgreSQL
	@docker exec -it ticketing_system_db psql -U py_arch_lab -d ticketing_system_db

# ==============================================================================
# 🧪 TESTING
# ==============================================================================

.PHONY: test
test:  ## 🧪 Run unit tests
	@uv run pytest test/ --ignore=test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-verbose
test-verbose:  ## 🧪 Run tests with output (-vs)
	@uv run pytest test/ --ignore=test/service/e2e -vs $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-e2e
test-e2e:  ## 🧪 Run E2E tests
	@uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-bdd
test-bdd:  ## 🧪 Run BDD tests (Gherkin)
	@uv run pytest test/features/ -v $(filter-out $@,$(MAKECMDGOALS))

%:
	@:

# ==============================================================================
# 🔧 CODE QUALITY
# ==============================================================================

.PHONY: lint
lint:  ## 🔍 Check code style
	@uv run ruff check .

.PHONY: format
format:  ## ✨ Format code
	@uv run ruff format .

.PHONY: pyre
pyre:  ## 🔬 Type checking
	@uv run pyrefly check

.PHONY: clean
clean:  ## 🧹 Remove cache files
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name ".DS_Store" -delete

# ==============================================================================
# 🐳 DOCKER - PRIMARY WORKFLOW
# ==============================================================================

.PHONY: dsu
dsu:  ## 🚀 Start Docker stack
	@docker-compose -f docker-compose.local.yml build
	@docker-compose -f docker-compose.local.yml up -d
	@echo "✅ Stack started!"
	@echo "   🔀 Load Balancer: http://localhost (nginx)"
	@echo "   🌐 API Gateway:   http://localhost:8000"
	@echo "   📚 Ticketing:     http://localhost:8100/docs"
	@echo "   🪑 Seat Res:      http://localhost:8200/docs"
	@echo "   📊 Kafka UI:      http://localhost:8080"
	@echo "   📈 Grafana:       http://localhost:3000"

.PHONY: dsd
dsd:  ## 🛑 Stop Docker stack
	@docker-compose -f docker-compose.local.yml down

.PHONY: dsr
dsr:  ## 🔄 Restart services
	@docker-compose -f docker-compose.local.yml restart ticketing-service seat-reservation-service

.PHONY: dr
dr:  ## 🔨 Rebuild services
	@docker-compose -f docker-compose.local.yml build ticketing-service seat-reservation-service
	@docker-compose -f docker-compose.local.yml up -d ticketing-service seat-reservation-service

# ==============================================================================
# 📈 SERVICE SCALING (Nginx Load Balancer)
# ==============================================================================

.PHONY: scale-up
scale-up:  ## 🚀 Scale services (usage: make scale-up T=3 R=2)
	@if [ -z "$(T)" ] || [ -z "$(R)" ]; then \
		echo "Usage: make scale-up T=<ticketing_count> R=<reservation_count>"; \
		echo "Example: make scale-up T=3 R=2"; \
		exit 1; \
	fi
	@echo "📈 Scaling services: ticketing=$(T), reservation=$(R)"
	@docker-compose -f docker-compose.local.yml up -d --scale ticketing-service=$(T) --scale seat-reservation-service=$(R) --no-recreate
	@echo "✅ Scaled successfully!"
	@docker-compose -f docker-compose.local.yml ps ticketing-service seat-reservation-service

.PHONY: scale-down
scale-down:  ## 📉 Scale down to 1 instance each
	@echo "📉 Scaling down to 1 instance each..."
	@docker-compose -f docker-compose.local.yml up -d --scale ticketing-service=1 --scale seat-reservation-service=1 --no-recreate
	@echo "✅ Scaled down successfully!"

.PHONY: scale-ticketing
scale-ticketing:  ## 🎫 Scale only ticketing service (usage: make scale-ticketing N=3)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-ticketing N=<count>"; \
		echo "Example: make scale-ticketing N=5"; \
		exit 1; \
	fi
	@echo "📈 Scaling ticketing-service to $(N) instances..."
	@docker-compose -f docker-compose.local.yml up -d --scale ticketing-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose -f docker-compose.local.yml ps ticketing-service

.PHONY: scale-reservation
scale-reservation:  ## 🪑 Scale only reservation service (usage: make scale-reservation N=2)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-reservation N=<count>"; \
		echo "Example: make scale-reservation N=3"; \
		exit 1; \
	fi
	@echo "📈 Scaling seat-reservation-service to $(N) instances..."
	@docker-compose -f docker-compose.local.yml up -d --scale seat-reservation-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose -f docker-compose.local.yml ps seat-reservation-service

.PHONY: scale-status
scale-status:  ## 📊 Show current scaling status
	@echo "📊 Current service instances:"
	@docker-compose -f docker-compose.local.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | grep -E "(ticketing-service|seat-reservation-service|nginx)"

.PHONY: dra
dra:  ## 🚀 Complete Docker reset (down → up → migrate → seed)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo "⚠️  This will stop containers and remove volumes"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@docker-compose -f docker-compose.local.yml down -v
	@docker-compose -f docker-compose.local.yml up -d
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
	@$(MAKE) ds
	@echo "✅ ==================== RESET COMPLETED ===================="

.PHONY: dm
dm:  ## 🗄️ Run migrations in Docker
	@echo "🗄️  Running database migrations..."
	@docker-compose -f docker-compose.local.yml exec ticketing-service uv run alembic upgrade head
	@echo "✅ Migrations completed"

.PHONY: ds
ds:  ## 🌱 Seed data in Docker
	@docker-compose -f docker-compose.local.yml exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/seed_data.py"

.PHONY: tdt
tdt:  ## 🧪 Run tests in Docker
	@docker-compose -f docker-compose.local.yml exec ticketing-service uv run pytest test/ --ignore=test/service/e2e -v

.PHONY: tde2e
tde2e:  ## 🧪 Run E2E tests in Docker
	@docker-compose -f docker-compose.local.yml exec ticketing-service uv run pytest test/service/e2e -v

.PHONY: tdinfra
tdinfra:  ## 🏗️ Run infrastructure tests in Docker
	@echo "🏗️  Testing infrastructure components in Docker..."
	@docker-compose -f docker-compose.local.yml exec ticketing-service uv run pytest test/infrastructure/ -v --tb=short
	@echo "✅ Infrastructure tests complete!"

.PHONY: tdci
tdci:  ## 🤖 Run CI tests (exclude infra, api, e2e)
	@docker-compose exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/infrastructure \
		-m "not api and not infra and not e2e" \
		-v

.PHONY: dsh
dsh:  ## 🐚 Shell into Ticketing Service
	@docker-compose exec ticketing-service bash

.PHONY: dal
dal:  ## 📋 View application logs
	@docker-compose logs -f ticketing-service seat-reservation-service

# ==============================================================================
# ⚡ LOAD TESTING
# ==============================================================================

.PHONY: ltb
ltb:  ## 🔨 Build Go load test binary
	@cd script/go_client && go build -o loadtest main.go

.PHONY: ltt
ltt:  ## 🧪 Tiny load test (10 requests, 10 workers, 10 clients)
	@cd script/go_client && ./loadtest -requests 10 -concurrency 10 -clients 10

.PHONY: ltq
ltq:  ## ⚡ Quick load test (2 processes × 250 requests, 25 workers each)
	@echo "🚀 Starting 2 parallel load test processes..."
	@cd script/go_client && \
		./loadtest -requests 250 -concurrency 25 -clients 25 & \
		wait
	@echo "✅ All parallel load tests completed"

.PHONY: ltf
ltf:  ## 💪 Full load test (50K requests, 100 workers, 100 clients)
	@cd script/go_client && ./loadtest -requests 50000 -concurrency 100 -clients 100

.PHONY: ltp
ltp:  ## 🚀 Parallel load test (4 processes × 25 requests × 10 workers = 100 total concurrent)
	@echo "🚀 Starting 4 parallel load test processes..."
	@cd script/go_client && \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		wait
	@echo "✅ All parallel load tests completed"

.PHONY: k6-smoke
k6-smoke:  ## 🔍 k6 smoke test
	@k6 run script/k6/smoke-test.js

.PHONY: k6-load
k6-load:  ## 📊 k6 load test
	@k6 run script/k6/load-test.js

.PHONY: k6-stress
k6-stress:  ## 💪 k6 stress test
	@k6 run script/k6/stress-test.js

# ==============================================================================
# 🌩️ AWS CDK (API GATEWAY)
# ==============================================================================

.PHONY: lsu
lsu:  ## 🌩️ Start LocalStack
	@docker-compose up -d localstack
	@echo "⏳ Waiting for LocalStack..."
	@sleep 10
	@echo "✅ LocalStack ready at http://localhost:4566"

.PHONY: lsd
lsd:  ## 🛑 Stop LocalStack
	@docker-compose stop localstack

.PHONY: cdk-bootstrap
cdk-bootstrap:  ## 🏗️ Bootstrap CDK (first time only)
	@cd deployment/cdk && \
		AWS_ACCESS_KEY_ID=test \
		AWS_SECRET_ACCESS_KEY=test \
		AWS_DEFAULT_REGION=us-east-1 \
		uv run cdklocal bootstrap

.PHONY: cdk-deploy
cdk-deploy:  ## 🚀 Deploy API Gateway
	@cd deployment/cdk && \
		AWS_ACCESS_KEY_ID=test \
		AWS_SECRET_ACCESS_KEY=test \
		AWS_DEFAULT_REGION=us-east-1 \
		uv run cdklocal deploy --require-approval never
	@echo "✅ API Gateway deployed!"
	@echo "   🌐 Endpoint: http://localhost:8000"
	@echo "   📋 Test: make cdk-test"

.PHONY: cdk-test
cdk-test:  ## 🧪 Test API Gateway
	@API_ID=$$(AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 apigateway get-rest-apis --query 'items[?name==`Ticketing System API`].id' --output text 2>/dev/null); \
	if [ -n "$$API_ID" ]; then \
		echo "✅ Testing API $$API_ID"; \
		curl -s "http://localhost:4566/restapis/$$API_ID/prod/_user_request_/api/event" | python3 -m json.tool | head -15; \
	else \
		echo "❌ API not found. Run 'make cdk-deploy' first"; \
	fi

# ==============================================================================
# 🌊 KAFKA
# ==============================================================================

.PHONY: ka
ka:  ## 🧹 Clean Kafka + Kvrocks + RocksDB
	@PYTHONPATH=. uv run python script/clean_all.py

.PHONY: ks
ks:  ## 📊 Kafka status
	@docker-compose ps kafka1 kafka2 kafka3
	@echo "🌐 Kafka UI: http://localhost:8080"

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
	@echo "  dra         - Complete Docker reset (recommended)"
	@echo "  dsu         - Start Docker stack"
	@echo "  reset       - Local reset (Kafka + DB + seed)"
	@echo ""
	@echo "🐳 DOCKER (Recommended)"
	@echo "  dsu/dsd/dsr/dr/dra/dm/ds/dt/de2e/dsh/dal"
	@echo ""
	@echo "🗄️  DATABASE"
	@echo "  migrate-up/down/new/history, psql"
	@echo ""
	@echo "🧪 TESTING"
	@echo "  test, test-verbose, test-e2e, test-bdd"
	@echo ""
	@echo "🔧 CODE"
	@echo "  format, lint, pyre, clean"
	@echo ""
	@echo "⚡ LOAD TESTING"
	@echo "  ltb, ltq, ltf, k6-smoke, k6-load, k6-stress"
	@echo ""
	@echo "🌩️  CDK (API Gateway)"
	@echo "  lsu, lsd, cdk-bootstrap, cdk-deploy, cdk-test"
	@echo ""
	@echo "🌊 KAFKA"
	@echo "  ka, ks"
	@echo ""
	@echo "💡 Examples:"
	@echo "  make dra                                # Fresh start with Docker"
	@echo "  make test test/service/                 # Test specific directory"
	@echo "  make migrate-new MSG='add field'        # Create migration"
	@echo ""
	@echo "📚 Docs: COMMANDS.md | DOCKER_GUIDE.md | spec/CONSTITUTION.md"
