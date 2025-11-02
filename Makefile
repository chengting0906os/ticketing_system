# Ticketing System - Simplified Makefile
ALEMBIC_CONFIG = alembic.ini

# AWS Configuration (can be overridden via environment variables)
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")


# ==============================================================================
# 📨 KAFKA CONSUMERS
# ==============================================================================

.PHONY: c-d-build c-start c-stop c-tail c-status
c-d-build:  ## 🔨 Build consumer images
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml build

c-start:  ## 🚀 Start consumer containers (4+4)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-consumer=4 --scale seat-reservation-consumer=4

c-stop:  ## 🛑 Stop consumer containers
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml stop ticketing-consumer seat-reservation-consumer
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml rm -f ticketing-consumer seat-reservation-consumer

c-tail:  ## 📝 Tail consumer logs
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml logs -f ticketing-consumer seat-reservation-consumer

c-status:  ## 📊 Consumer status
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml ps ticketing-consumer seat-reservation-consumer

# ==============================================================================
# 🗄️ DATABASE
# ==============================================================================

.PHONY: migrate-up migrate-down migrate-new migrate-history psql
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
# 🐳 DOCKER - PRIMARY WORKFLOW
# ==============================================================================

.PHONY: d-s-rs s-d-build

d-s-rs:  ## 🔄 Restart services
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml restart ticketing-service

s-d-build:  ## 🔨 Rebuild services
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml build ticketing-service

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
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=$(T) --no-recreate
	@echo "✅ Scaled successfully!"
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml ps ticketing-service

scale-down:  ## 📉 Scale down to 1 instance each
	@echo "📉 Scaling down to 1 instance each..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=1 --no-recreate
	@echo "✅ Scaled down successfully!"

scale-ticketing:  ## 🎫 Scale only ticketing service (usage: make scale-ticketing N=3)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-ticketing N=<count>"; \
		echo "Example: make scale-ticketing N=5"; \
		exit 1; \
	fi
	@echo "📈 Scaling ticketing-service to $(N) instances..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml ps ticketing-service

scale-reservation:  ## 🪑 Scale only reservation service (usage: make scale-reservation N=2)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-reservation N=<count>"; \
		echo "Example: make scale-reservation N=3"; \
		exit 1; \
	fi
	@echo "📈 Scaling seat-reservation-service to $(N) instances..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale seat-reservation-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml ps seat-reservation-service

scale-status:  ## 📊 Show current scaling status
	@echo "📊 Current service instances:"
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | grep -E "(ticketing-service|seat-reservation-service|nginx)"

dra:  ## 🚀 Complete Docker reset (down → up → migrate → reset-kafka → seed → start-consumers)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo "⚠️  This will stop all containers and remove volumes"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo "🛑 Stopping everything..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml down -v
	@echo "🚀 Starting all services (consumers first, then API)..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d \
		--scale ticketing-consumer=4 \
		--scale seat-reservation-consumer=4
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
	@echo "   🌐 API:          http://localhost:8100/docs"
	@echo "   📊 Kafka UI:     http://localhost:8080"
	@echo "   📈 Grafana:      http://localhost:3000"
	@echo "   🔍 Jaeger:       http://localhost:16686"
	@echo "   📨 Consumers:    8 containers (4 ticketing + 4 seat reservation)"
	@echo ""
	@echo "💡 monitor: make c-status | make c-tail"

.PHONY: dm ds drk tdt tdinfra tdci
dm:  ## 🗄️ Run migrations in Docker
	@echo "🗄️  Running database migrations..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml exec ticketing-service uv run alembic upgrade head
	@echo "✅ Migrations completed"

ds:  ## 🌱 Seed data in Docker
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/seed_data.py"

drk:  ## 🌊 Reset Kafka in Docker
	@echo "🌊 Resetting Kafka..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/reset_kafka.py"
	@echo "✅ Kafka reset completed"

tdt:  ## 🧪 Run tests in Docker (excludes E2E, deployment, infra, skipped features)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/deployment \
		--ignore=test/infrastructure \
		--ignore=test/service/ticketing/integration/features/booking_insufficient_seats.feature \
		-v

tdinfra:  ## 🏗️ Run infrastructure tests in Docker
	@echo "🏗️  Testing infrastructure components in Docker..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml exec ticketing-service uv run pytest test/infrastructure/ -v --tb=short
	@echo "✅ Infrastructure tests complete!"

tdci:  ## 🤖 Run CI tests (exclude infra, api, e2e, deployment)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/infrastructure \
		--ignore=test/deployment \
		-m "not api and not infra and not e2e" \
		-v

# ==============================================================================
# ⚡ LOAD TESTING
# ==============================================================================

.PHONY: go-build ltt lts ltm ltl ltf ltp k6-smoke k6-load k6-stress
go-build:  ## 🔨 Build Go load test binary
	@cd script/go_client && go build -o loadtest main.go

ltt:  ## 🧪 Tiny load test (10 requests, 10 workers, 10 clients)
	@cd script/go_client && ./loadtest -requests 10 -concurrency 5 -clients 5

lts:  ## 🧪 Small load test (10 requests, 10 workers, 10 clients)
	@cd script/go_client && ./loadtest -requests 100 -concurrency 10 -clients 10

ltm:  ## ⚡ Medium load test (2 processes × 250 requests, 25 workers each)
	@cd script/go_client && \
		./loadtest -requests 500 -concurrency 25 -clients 25 & \

ltl:  ## ⚡ Large load test (2 processes × 250 requests, 25 workers each)
	@cd script/go_client && \
		./loadtest -requests 10000 -concurrency 50 -clients 50 & \

ltf:  ## 💪 Full load test (50K requests, 100 workers, 100 clients)
	@cd script/go_client && ./loadtest -requests 50000 -concurrency 100 -clients 100

ltp:  ## 🚀 Parallel load test (4 processes × 25 requests × 10 workers = 100 total concurrent)
	@echo "🚀 Starting 4 parallel load test processes..."
	@cd script/go_client && \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		./loadtest -requests 25 -concurrency 10 -clients 10 & \
		wait
	@echo "✅ All parallel load tests completed"

k6-smoke:  ## 🔍 k6 smoke test
	@k6 run script/k6/smoke-test.js

k6-load:  ## 📊 k6 load test
	@k6 run script/k6/load-test.js

k6-stress:  ## 💪 k6 stress test
	@k6 run script/k6/stress-test.js

# ==============================================================================
# 🌩️ AWS CDK DEPLOYMENT
# ==============================================================================

.PHONY: cdk-synth cdk-diff deploy destroy cdk-deploy-dev cdk-deploy-loadtest cdk-destroy cdk-ls
cdk-synth:  ## 🔍 Synthesize CDK stack (validate infrastructure code)
	@echo "🔍 Synthesizing CDK stack..."
	@CDK_DEFAULT_ACCOUNT=123456789012 \
		CDK_DEFAULT_REGION=us-west-2 \
		uv run cdk synth --no-lookups
	@echo "✅ CDK synthesis completed!"

cdk-diff:  ## 📊 Show differences between deployed and local stack
	@echo "📊 Comparing stack differences..."
	@CDK_DEFAULT_ACCOUNT=123456789012 \
		CDK_DEFAULT_REGION=us-west-2 \
		uv run cdk diff

deploy:  ## 🚀 One-click deployment (infrastructure + Docker images + health check)
	@echo "🚀 Starting one-click deployment..."
	@./deployment/deploy-all.sh

destroy:  ## 💣 One-click shutdown (delete all AWS resources to stop billing)
	@echo "💣 Starting one-click shutdown..."
	@./deployment/destroy-all.sh

cdk-deploy-dev:  ## 🏗️ Deploy CDK infrastructure only (no Docker images)
	@echo "🚀 Deploying to AWS development environment..."
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@uv run cdk deploy --all --require-approval never
	@echo "✅ Deployment completed!"

cdk-deploy-loadtest:  ## 🧪 Deploy loadtest stack only (Fargate Spot 32GB)
	@echo "🧪 Deploying loadtest infrastructure..."
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@uv run cdk deploy TicketingLoadTestStack --require-approval never
	@echo "✅ Loadtest stack deployed!"
	@echo "📋 Next: Use ECS Console or AWS CLI to run tasks"

cdk-destroy:  ## 🗑️ Destroy CDK stacks only (use 'make destroy' for complete cleanup)
	@echo "⚠️  WARNING: This will destroy all AWS resources!"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@uv run cdk destroy --all
	@echo "✅ All stacks destroyed"

cdk-ls:  ## 📋 List all CDK stacks
	@CDK_DEFAULT_ACCOUNT=123456789012 \
		CDK_DEFAULT_REGION=us-west-2 \
		uv run cdk list


# ==============================================================================
# 🐳 AWS ECR (Elastic Container Registry)
# ==============================================================================

.PHONY: ecr-push-all ecr-push-ticketing ecr-push-reservation ecr-push-staging ecr-push-dev ecr-login ecr-list ecr-cleanup
ecr-push-all:  ## 🚀 Build and push all services to ECR (production)
	@echo "🚀 Building and pushing all services to ECR (production)..."
	@./deployment/script/ecr-push.sh production all

ecr-push-ticketing:  ## 🎫 Build and push ticketing service to ECR (production)
	@echo "🎫 Building and pushing ticketing-service to ECR (production)..."
	@./deployment/script/ecr-push.sh production ticketing

ecr-push-reservation:  ## 🪑 Build and push seat-reservation service to ECR (production)
	@echo "🪑 Building and pushing seat-reservation-service to ECR (production)..."
	@./deployment/script/ecr-push.sh production seat-reservation

ecr-push-staging:  ## 🧪 Build and push all services to ECR (staging)
	@echo "🧪 Building and pushing all services to ECR (staging)..."
	@./deployment/script/ecr-push.sh staging all

ecr-push-dev:  ## 🔧 Build and push all services to ECR (development)
	@echo "🔧 Building and pushing all services to ECR (development)..."
	@./deployment/script/ecr-push.sh development all

ecr-login:  ## 🔐 Login to AWS ECR
	@echo "🔐 Logging in to AWS ECR..."
	@aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
	@echo "✅ ECR login successful"

ecr-list:  ## 📋 List Docker images in ECR repositories
	@echo "📋 Images in ticketing-service repository:"
	@aws ecr list-images --repository-name ticketing-service --region $(AWS_REGION) --output table || echo "Repository not found"
	@echo ""
	@echo "📋 Images in seat-reservation-service repository:"
	@aws ecr list-images --repository-name seat-reservation-service --region $(AWS_REGION) --output table || echo "Repository not found"

ecr-cleanup:  ## 🧹 Remove old ECR images (keep last 10 per environment)
	@echo "🧹 Cleaning up old ECR images..."
	@echo "⚠️  This will keep only the last 10 images per environment tag"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@for repo in ticketing-service seat-reservation-service; do \
		echo "Cleaning $$repo..."; \
		aws ecr list-images --repository-name $$repo --region $(AWS_REGION) \
			--query 'imageIds[?type(imageTag)!=`null`]|sort_by(@, &imageTag)|[0:-10].[imageDigest]' \
			--output text | xargs -I {} aws ecr batch-delete-image \
			--repository-name $$repo --region $(AWS_REGION) --image-ids imageDigest={} || true; \
	done
	@echo "✅ Cleanup completed"

# ==============================================================================
# 🌊 KAFKA
# ==============================================================================

.PHONY: ka ks
ka:  ## 🧹 Clean Kafka + Kvrocks + RocksDB
	@PYTHONPATH=. uv run python script/clean_all.py

ks:  ## 📊 Kafka status
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml ps kafka1 kafka2 kafka3
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
	@echo "  dsu/dsd/dsr/dr/dra/dm/drk/ds/dt/de2e/dsh/dal"
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
	@echo "🌩️  AWS CDK DEPLOYMENT"
	@echo "  cdk-synth, cdk-diff, cdk-deploy-dev, cdk-deploy-loadtest, cdk-destroy, cdk-ls"
	@echo ""
	@echo "📊 AWS ECS MONITORING"
	@echo "  monitor-ecs, monitor-all"
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
