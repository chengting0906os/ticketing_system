# Ticketing System - Simplified Makefile
ALEMBIC_CONFIG = alembic.ini

# AWS Configuration (can be overridden via environment variables)
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")


# ==============================================================================
# 📨 KAFKA CONSUMERS
# ==============================================================================

.PHONY: c-d-build c-start c-stop c-restart c-tail c-status
c-d-build:  ## 🔨 Build consumer images
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml build

c-start:  ## 🚀 Start consumer containers (4+4)
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml up -d --scale ticketing-consumer=4 --scale seat-reservation-consumer=4

c-stop:  ## 🛑 Stop consumer containers
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml stop ticketing-consumer seat-reservation-consumer
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml rm -f ticketing-consumer seat-reservation-consumer

c-restart:  ## 🔄 Restart consumer containers (hot reload code changes)
	@echo "🔄 Restarting consumers to reload code changes..."
	@docker-compose -f docker-compose.yml -f docker-compose.consumers.yml restart ticketing-consumer seat-reservation-consumer
	@echo "✅ Consumers restarted"

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
	@echo ""

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

# Build Targets
.PHONY: go-build-concurrent go-build-reserved g-b-c g-b-r

go-build-concurrent g-b-c:  ## 🔨 Build Go concurrent load test binary
	@cd script/go_client && go build -o concurrent_loadtest concurrent_loadtest.go types.go

go-build-reserved g-b-r:  ## 🔨 Build Go reserved load test binary
	@cd script/go_client && go build -o reserved_loadtest reserved_loadtest.go types.go



# Concurrent Load Test (Pressure Testing)
.PHONY: go-clt-t go-clt-s go-clt-m go-clt-l go-clt-f

go-clt-t:  ## 🧪 Concurrent Load Test - Tiny (10 requests, 5 concurrency, 5 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 10 -concurrency 5 -clients 5

go-clt-s:  ## 🧪 Concurrent Load Test - Small (100 requests, 10 concurrency, 10 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 100 -concurrency 10 -clients 10

go-clt-m:  ## ⚡ Concurrent Load Test - Medium (5000 requests, 50concurrency, 50 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 5000 -concurrency 25 -clients 25

go-clt-l:  ## ⚡ Concurrent Load Test - Large (10000 requests, 50 concurrency, 50 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 10000 -concurrency 50 -clients 50

go-clt-f:  ## 💪 Concurrent Load Test - Full (50000 requests, 100 concurrency, 100 clients)
	@cd script/go_client && ./concurrent_loadtest -requests 50000 -concurrency 100 -clients 100


# Reserved Load Test (Sellout Testing)
.PHONY: go-rlt

go-rlt:  ## 🔥 Reserved Load Test - Buys all seats (random 1-4 tickets, max 5 per subsection)
	@echo "🔥 Running reserved load test (Go)..."
	@if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "📊 Production mode: 50,000 seats (100 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env production -event 1 -workers 100 -host http://localhost:8100; \
	elif [ "$(DEPLOY_ENV)" = "development" ]; then \
		echo "📊 Development mode: 5,000 seats (50 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env development -event 1 -workers 50 -host http://localhost:8100; \
	else \
		echo "📊 Local dev mode: 500 seats (20 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env local_dev -event 1 -workers 20 -host http://localhost:8100; \
	fi


# Legacy Aliases (for backward compatibility)
.PHONY: ltt lts ltm ltl ltf ltp

ltt: go-clt-t  ## 🧪 [LEGACY] Tiny load test → go-clt-t

lts: go-clt-s  ## 🧪 [LEGACY] Small load test → go-clt-s

ltm: go-clt-m  ## ⚡ [LEGACY] Medium load test → go-clt-m

ltl: go-clt-l  ## ⚡ [LEGACY] Large load test → go-clt-l

ltf: go-clt-f  ## 💪 [LEGACY] Full load test → go-clt-f

ltp:  ## 🚀 [LEGACY] Parallel load test (4 processes × 25 requests)
	@echo "🚀 Starting 4 parallel load test processes..."
	@cd script/go_client && \
		./concurrent_loadtest -requests 25 -concurrency 10 -clients 10 & \
		./concurrent_loadtest -requests 25 -concurrency 10 -clients 10 & \
		./concurrent_loadtest -requests 25 -concurrency 10 -clients 10 & \
		./concurrent_loadtest -requests 25 -concurrency 10 -clients 10 & \
		wait
	@echo "✅ All parallel load tests completed"

# k6 Load Tests
.PHONY: k6-smoke k6-load k6-stress

k6-smoke:  ## 🔍 k6 smoke test
	@k6 run script/k6/smoke-test.js

k6-load:  ## 📊 k6 load test
	@k6 run script/k6/load-test.js

k6-stress:  ## 💪 k6 stress test
	@k6 run script/k6/stress-test.js

# ==============================================================================
# 🌩️ AWS CDK DEPLOYMENT
# ==============================================================================

.PHONY: cdk-synth cdk-diff deploy destroy dev-deploy-all prod-deploy-all cdk-deploy-loadtest cdk-destroy cdk-ls cdk-check-env
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

cdk-check-env:  ## 🔍 Check current Aurora configuration and environment
	@echo "🔍 Checking Aurora configuration..."
	@echo "Current Aurora MaxCapacity: $$(aws rds describe-db-clusters --db-cluster-identifier ticketing-aurora-cluster --query 'DBClusters[0].ServerlessV2ScalingConfiguration.MaxCapacity' --output text 2>/dev/null || echo 'Not deployed yet')"
	@echo "Config environments:"
	@echo "  - development: max_acu = 8"
	@echo "  - production:  max_acu = 64"
	@echo ""
	@echo "💡 Use 'make dev-deploy-all' or 'make prod-deploy-all' to deploy"

dev-deploy-all:  ## 🔧 Deploy all stacks (DEVELOPMENT environment: Aurora 0.5-8 ACU)
	@echo "🔧 Deploying to AWS development environment..."
	@echo "📋 Configuration:"
	@echo "   - Aurora ACU: 0.5-8 (minimal for testing)"
	@echo "   - ECS Tasks: 1-2 per service"
	@echo "   - Consumers: 1-4 tasks max"
	@echo ""
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@DEPLOY_ENV=development uv run cdk deploy --all --require-approval never
	@echo "✅ Development deployment completed!"

prod-deploy-all:  ## 🚀 Deploy all stacks (PRODUCTION environment: Aurora 0.5-64 ACU)
	@echo "🚀 Deploying to AWS production environment..."
	@echo "📋 Configuration:"
	@echo "   - Aurora ACU: 0.5-64 (auto-scaling for 10K TPS)"
	@echo "   - ECS Tasks: 1-4 per service"
	@echo "   - Consumers: 1-200 tasks max (100 vCPU capacity)"
	@echo ""
	@echo "⚠️  WARNING: Production configuration uses higher resources!"
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@DEPLOY_ENV=production uv run cdk deploy --all --require-approval never
	@echo "✅ Production deployment completed!"

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
# ☁️ AWS ECS SERVICE MANAGEMENT
# ==============================================================================

# Default values
ENV ?= dev
SERVICE ?= api

.PHONY: aws-reset aws-migrate aws-reset-kafka aws-seed aws-stop aws-start aws-status aws-logs aws-logs-ticketing aws-logs-reservation aws-setup-secrets aws-db-list aws-db-schema aws-db-migrations aws-db-query aws-help

aws-reset:  ## 🚀 Complete AWS reset (restart services → migrate → reset-kafka → seed) - Cloud version of 'make dra'
	@echo "🚀 ==================== AWS COMPLETE RESET ===================="
	@echo "⚠️  This will:"
	@echo "   1. Restart all ECS services (API + Consumers)"
	@echo "   2. Run database migrations"
	@echo "   3. Reset Kafka topics"
	@echo "   4. Seed initial data"
	@echo ""
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "🔄 Step 1/4: Restarting ECS services..."
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-api-service --force-new-deployment \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-ticketing-consumer-service --force-new-deployment \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-reservation-consumer-service --force-new-deployment \
		--query 'service.serviceName' --output text
	@echo "✅ All services restarted"
	@echo ""
	@echo "⏳ Step 2/4: Waiting for API service to be healthy (30s)..."
	@sleep 30
	@echo ""
	@echo "🗄️  Step 3/4: Running migrations..."
	@$(MAKE) aws-migrate
	@echo ""
	@echo "🌊 Step 4/4: Resetting Kafka topics..."
	@$(MAKE) aws-reset-kafka
	@echo ""
	@echo "🌱 Step 5/5: Seeding data..."
	@$(MAKE) aws-seed
	@echo ""
	@echo "✅ ==================== AWS RESET COMPLETE ===================="
	@echo "   📊 Check status: make aws-status"
	@echo "   🔍 View logs:    make aws-logs"
	@echo ""

aws-migrate:  ## 🗄️ Run migrations on AWS Aurora (via ECS task)
	@echo "🗄️  Running database migrations..."
	@TASK_DEF=$$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-api-service --region us-west-2 --query 'services[0].taskDefinition' --output text); \
	aws ecs run-task \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$(shell aws ec2 describe-subnets --filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" --query 'Subnets[0].SubnetId' --output text)],securityGroups=[$(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=*AuroraSecurityGroup*" --query 'SecurityGroups[0].GroupId' --output text)]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["uv","run","alembic","upgrade","head"]}]}' \
		--query 'tasks[0].taskArn' --output text
	@echo "✅ Migration task started"

aws-reset-kafka:  ## 🌊 Reset Kafka topics on AWS (connect to EC2 and reset)
	@echo "🌊 Resetting Kafka topics..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters 'commands=["cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic ticketing-events || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic seat-reservation-events || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic ticketing-events --partitions 6 --replication-factor 3 || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic seat-reservation-events --partitions 6 --replication-factor 3 || true"]' \
		--query 'Command.CommandId' --output text
	@echo "✅ Kafka topics reset"

aws-seed:  ## 🌱 Seed data on AWS Aurora (via ECS task)
	@echo "🌱 Seeding initial data..."
	@TASK_DEF=$$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-api-service --region us-west-2 --query 'services[0].taskDefinition' --output text); \
	aws ecs run-task \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$(shell aws ec2 describe-subnets --filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" --query 'Subnets[0].SubnetId' --output text)],securityGroups=[$(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=*AuroraSecurityGroup*" --query 'SecurityGroups[0].GroupId' --output text)]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["uv","run","python","-m","script.seed_data"]}]}' \
		--query 'tasks[0].taskArn' --output text
	@echo "✅ Seed task started"

aws-stop:  ## 🛑 Stop ALL AWS services (ECS + EC2 Kafka, keep Aurora only)
	@echo "🛑 Stopping ALL AWS services..."
	@echo "⚠️  This will:"
	@echo "   - Scale all ECS services to 0"
	@echo "   - Stop EC2 Kafka instance"
	@echo "   - Keep Aurora running (minimal cost)"
	@echo ""
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "📦 Scaling ECS services to 0..."
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-api-service --desired-count 0 \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-ticketing-consumer-service --desired-count 0 \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-reservation-consumer-service --desired-count 0 \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service kvrocks-master --desired-count 0 \
		--query 'service.serviceName' --output text
	@echo "✅ All ECS services scaled to 0"
	@echo ""
	@echo "🔌 Stopping EC2 Kafka instance..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ "$$INSTANCE_ID" != "None" ] && [ -n "$$INSTANCE_ID" ]; then \
		aws ec2 stop-instances --instance-ids $$INSTANCE_ID --query 'StoppingInstances[0].InstanceId' --output text; \
		echo "✅ EC2 Kafka stopped: $$INSTANCE_ID"; \
	else \
		echo "⚠️  EC2 Kafka already stopped or not found"; \
	fi
	@echo ""
	@echo "✅ ==================== ALL SERVICES STOPPED ===================="
	@echo "💰 Cost now: ~$0.01/hour (Aurora Serverless v2 at 0.5 ACU minimum)"
	@echo "💡 To restart: make aws-start"

aws-start:  ## ▶️  Start ALL AWS services (ECS + EC2 Kafka)
	@echo "▶️  Starting ALL AWS services..."
	@echo ""
	@echo "🔌 Starting EC2 Kafka instance..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=stopped" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ "$$INSTANCE_ID" != "None" ] && [ -n "$$INSTANCE_ID" ]; then \
		aws ec2 start-instances --instance-ids $$INSTANCE_ID --query 'StartingInstances[0].InstanceId' --output text; \
		echo "✅ EC2 Kafka starting: $$INSTANCE_ID"; \
		echo "⏳ Waiting 60s for Kafka to be ready..."; \
		sleep 60; \
	else \
		echo "⚠️  EC2 Kafka already running or not found"; \
	fi
	@echo ""
	@echo "📦 Scaling ECS services back to normal..."
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-api-service --desired-count 1 \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-ticketing-consumer-service --desired-count 2 \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-reservation-consumer-service --desired-count 2 \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service kvrocks-master --desired-count 1 \
		--query 'service.serviceName' --output text
	@echo ""
	@echo "✅ ==================== ALL SERVICES STARTED ===================="
	@echo "💡 Check status: make aws-status"

aws-status:  ## 📊 Check status of all AWS ECS services
	@echo "📊 ECS Services Status:"
	@aws ecs describe-services --cluster ticketing-cluster \
		--services ticketing-development-api-service \
		         ticketing-development-ticketing-consumer-service \
		         ticketing-development-reservation-consumer-service \
		--query 'services[].[serviceName,status,runningCount,desiredCount]' \
		--output table

aws-logs:  ## 🔍 Tail logs from AWS API service
	@echo "🔍 Tailing API service logs (Ctrl+C to exit)..."
	@LOG_GROUP=$$(aws ecs describe-task-definition \
		--task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-api-service --query 'services[0].taskDefinition' --output text | rev | cut -d'/' -f1 | rev) \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	aws logs tail $$LOG_GROUP --follow --format short

aws-logs-ticketing:  ## 🔍 Tail logs from AWS Ticketing Consumer
	@echo "🔍 Tailing Ticketing Consumer logs (Ctrl+C to exit)..."
	@LOG_GROUP=$$(aws ecs describe-task-definition \
		--task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-ticketing-consumer-service --query 'services[0].taskDefinition' --output text | rev | cut -d'/' -f1 | rev) \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	aws logs tail $$LOG_GROUP --follow --format short

aws-logs-reservation:  ## 🔍 Tail logs from AWS Reservation Consumer
	@echo "🔍 Tailing Reservation Consumer logs (Ctrl+C to exit)..."
	@LOG_GROUP=$$(aws ecs describe-task-definition \
		--task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-reservation-consumer-service --query 'services[0].taskDefinition' --output text | rev | cut -d'/' -f1 | rev) \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	aws logs tail $$LOG_GROUP --follow --format short

aws-db-list:  ## 🗄️ List all Aurora tables with row counts (via ECS task)
	@echo "🗄️  Listing Aurora tables..."
	@TASK_DEF=$$(aws ecs describe-services \
		--cluster ticketing-cluster \
		--services ticketing-development-api-service \
		--region $(AWS_REGION) \
		--query 'services[0].taskDefinition' --output text); \
	SUBNET=$$(aws ec2 describe-subnets \
		--region $(AWS_REGION) \
		--filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" \
		--query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups \
		--region $(AWS_REGION) \
		--filters "Name=group-name,Values=*AuroraSecurityGroup*" \
		--query 'SecurityGroups[0].GroupId' --output text); \
	echo "Using task: $$TASK_DEF, Subnet: $$SUBNET, SG: $$SG"; \
	TASK_ARN=$$(aws ecs run-task \
		--region $(AWS_REGION) \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["python","deployment/script/aurora_inspect.py","list"]}]}' \
		--query 'tasks[0].taskArn' --output text); \
	echo "Task started: $$TASK_ARN"; \
	echo "Waiting for task to complete (this may take 1-2 minutes)..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --region $(AWS_REGION) --tasks $$TASK_ARN; \
	echo "Fetching logs..."; \
	LOG_GROUP=$$(aws ecs describe-task-definition \
		--region $(AWS_REGION) \
		--task-definition $$TASK_DEF \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	TASK_ID=$$(echo $$TASK_ARN | rev | cut -d'/' -f1 | rev); \
	aws logs get-log-events \
		--region $(AWS_REGION) \
		--log-group-name $$LOG_GROUP \
		--log-stream-name Container/Container/$$TASK_ID \
		--query 'events[*].message' --output text

aws-db-schema:  ## 📐 Show Aurora table schema (usage: make aws-db-schema TABLE=events)
	@if [ -z "$(TABLE)" ]; then \
		echo "❌ Usage: make aws-db-schema TABLE=<table_name>"; \
		echo "Example: make aws-db-schema TABLE=events"; \
		exit 1; \
	fi
	@echo "📐 Showing schema for table: $(TABLE)"
	@TASK_DEF=$$(aws ecs describe-services \
		--cluster ticketing-cluster \
		--services ticketing-development-api-service \
		--region $(AWS_REGION) \
		--query 'services[0].taskDefinition' --output text); \
	SUBNET=$$(aws ec2 describe-subnets \
		--region $(AWS_REGION) \
		--filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" \
		--query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups \
		--region $(AWS_REGION) \
		--filters "Name=group-name,Values=*AuroraSecurityGroup*" \
		--query 'SecurityGroups[0].GroupId' --output text); \
	TASK_ARN=$$(aws ecs run-task \
		--region $(AWS_REGION) \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["python","deployment/script/aurora_inspect.py","schema","$(TABLE)"]}]}' \
		--query 'tasks[0].taskArn' --output text); \
	echo "Task started: $$TASK_ARN"; \
	echo "Waiting for task to complete (this may take 1-2 minutes)..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --region $(AWS_REGION) --tasks $$TASK_ARN; \
	echo "Fetching logs..."; \
	LOG_GROUP=$$(aws ecs describe-task-definition \
		--region $(AWS_REGION) \
		--task-definition $$TASK_DEF \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	TASK_ID=$$(echo $$TASK_ARN | rev | cut -d'/' -f1 | rev); \
	aws logs get-log-events \
		--region $(AWS_REGION) \
		--log-group-name $$LOG_GROUP \
		--log-stream-name Container/Container/$$TASK_ID \
		--query 'events[*].message' --output text

aws-db-migrations:  ## 🔄 Check Aurora migration status (via ECS task)
	@echo "🔄 Checking migration status..."
	@TASK_DEF=$$(aws ecs describe-services \
		--cluster ticketing-cluster \
		--services ticketing-development-api-service \
		--region $(AWS_REGION) \
		--query 'services[0].taskDefinition' --output text); \
	SUBNET=$$(aws ec2 describe-subnets \
		--region $(AWS_REGION) \
		--filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" \
		--query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups \
		--region $(AWS_REGION) \
		--filters "Name=group-name,Values=*AuroraSecurityGroup*" \
		--query 'SecurityGroups[0].GroupId' --output text); \
	echo "Using task: $$TASK_DEF, Subnet: $$SUBNET, SG: $$SG"; \
	TASK_ARN=$$(aws ecs run-task \
		--region $(AWS_REGION) \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["python","deployment/script/aurora_inspect.py","migrations"]}]}' \
		--query 'tasks[0].taskArn' --output text); \
	echo "Task started: $$TASK_ARN"; \
	echo "Waiting for task to complete (this may take 1-2 minutes)..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --region $(AWS_REGION) --tasks $$TASK_ARN; \
	echo "Fetching logs..."; \
	LOG_GROUP=$$(aws ecs describe-task-definition \
		--region $(AWS_REGION) \
		--task-definition $$TASK_DEF \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	TASK_ID=$$(echo $$TASK_ARN | rev | cut -d'/' -f1 | rev); \
	aws logs get-log-events \
		--region $(AWS_REGION) \
		--log-group-name $$LOG_GROUP \
		--log-stream-name Container/Container/$$TASK_ID \
		--query 'events[*].message' --output text

aws-db-query:  ## 🔍 Query Aurora table data (usage: make aws-db-query TABLE=events LIMIT=10)
	@if [ -z "$(TABLE)" ]; then \
		echo "❌ Usage: make aws-db-query TABLE=<table_name> [LIMIT=<number>]"; \
		echo "Example: make aws-db-query TABLE=events LIMIT=10"; \
		exit 1; \
	fi
	@LIMIT=$${LIMIT:-10}; \
	echo "🔍 Querying table: $(TABLE) (limit: $$LIMIT)"; \
	TASK_DEF=$$(aws ecs describe-services \
		--cluster ticketing-cluster \
		--services ticketing-development-api-service \
		--region $(AWS_REGION) \
		--query 'services[0].taskDefinition' --output text); \
	SUBNET=$$(aws ec2 describe-subnets \
		--region $(AWS_REGION) \
		--filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" \
		--query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups \
		--region $(AWS_REGION) \
		--filters "Name=group-name,Values=*AuroraSecurityGroup*" \
		--query 'SecurityGroups[0].GroupId' --output text); \
	TASK_ARN=$$(aws ecs run-task \
		--region $(AWS_REGION) \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--overrides "{\"containerOverrides\":[{\"name\":\"Container\",\"command\":[\"python\",\"deployment/script/aurora_inspect.py\",\"query\",\"$(TABLE)\",\"--limit\",\"$$LIMIT\"]}]}" \
		--query 'tasks[0].taskArn' --output text); \
	echo "Task started: $$TASK_ARN"; \
	echo "Waiting for task to complete (this may take 1-2 minutes)..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --region $(AWS_REGION) --tasks $$TASK_ARN; \
	echo "Fetching logs..."; \
	LOG_GROUP=$$(aws ecs describe-task-definition \
		--region $(AWS_REGION) \
		--task-definition $$TASK_DEF \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	TASK_ID=$$(echo $$TASK_ARN | rev | cut -d'/' -f1 | rev); \
	aws logs get-log-events \
		--region $(AWS_REGION) \
		--log-group-name $$LOG_GROUP \
		--log-stream-name Container/Container/$$TASK_ID \
		--query 'events[*].message' --output text

aws-help:  ## ❓ Show AWS management commands help
	@echo "☁️  AWS ECS Service Management (Using AWS CLI)"
	@echo ""
	@echo "🚀 Quick Reset (like 'make dra' for local):"
	@echo "  make aws-reset              # Complete reset: restart + migrate + reset-kafka + seed"
	@echo ""
	@echo "⚡ Service Control:"
	@echo "  make aws-stop               # Stop ALL services (ECS + EC2 Kafka, keep Aurora only)"
	@echo "  make aws-start              # Start ALL services (ECS + EC2 Kafka)"
	@echo "  make aws-status             # Check all services status"
	@echo ""
	@echo "🔍 View Logs:"
	@echo "  make aws-logs               # Tail API service logs"
	@echo "  make aws-logs-ticketing     # Tail ticketing consumer logs"
	@echo "  make aws-logs-reservation   # Tail reservation consumer logs"
	@echo ""
	@echo "🗄️  Database Inspection:"
	@echo "  make aws-db-list            # List all tables with row counts"
	@echo "  make aws-db-migrations      # Check migration status"
	@echo "  make aws-db-schema TABLE=events         # Show table schema"
	@echo "  make aws-db-query TABLE=events LIMIT=10 # Query table data"
	@echo ""
	@echo "🔄 Individual Operations:"
	@echo "  make aws-migrate            # Run database migrations"
	@echo "  make aws-reset-kafka        # Reset Kafka topics"
	@echo "  make aws-seed               # Seed initial data"

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
	@echo "  reset       - Quick reset (Kafka + Kvrocks + DB + seed, no restart)"
	@echo "  dra         - Complete Docker reset (down → up → reset, slower)"
	@echo "  dsu         - Start Docker stack"
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
	@echo "☁️  AWS ECS SERVICE MANAGEMENT"
	@echo "  aws-restart, aws-status, aws-help"
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
