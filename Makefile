# Ticketing System - Simplified Makefile
ALEMBIC_CONFIG = alembic.ini

# AWS Configuration (can be overridden via environment variables)
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")

# ==============================================================================
# 🚀 QUICK START
# ==============================================================================

.PHONY: reset reset-all
reset:  ## 🔄 Reset Kafka + Database + Seed data
	@echo "🚀 Complete system reset..."
	@PYTHONPATH=. uv run python script/reset_kafka.py
	@PYTHONPATH=. DATABASE_TYPE=scylladb uv run python script/reset_scylladb.py
	@PYTHONPATH=. uv run python script/seed_data.py
	@echo "✅ Reset complete!"

reset-all: reset  ## 🔄 Reset + start services (DEPRECATED: use Docker)
	@echo "⚠️  Local services deprecated. Use 'make dra' for Docker"

# ==============================================================================
# 🗄️ DATABASE
# ==============================================================================

.PHONY: db-reset
db-reset:  ## 🔄 Reset ScyllaDB (drop & recreate keyspace)
	@echo "🔄 Resetting ScyllaDB..."
	@DATABASE_TYPE=scylladb uv run python script/reset_scylladb.py
	@echo "✅ Database reset complete!"

.PHONY: db-init
db-init:  ## 🏗️ Initialize ScyllaDB schema
	@echo "🏗️ Initializing ScyllaDB schema..."
	@docker exec -i scylladb1 cqlsh -u cassandra -p cassandra < src/platform/database/scylla_schemas.cql
	@echo "✅ Schema initialization completed"

.PHONY: cqlsh
cqlsh:  ## 🗄️ Connect to ScyllaDB
	@docker exec -it scylladb1 cqlsh -u cassandra -p cassandra

# ==============================================================================
# 🧪 TESTING
# ==============================================================================

.PHONY: test
test:  ## 🧪 Run unit tests (excludes CDK and E2E)
	@uv run pytest test/ --ignore=test/service/e2e -m "not cdk" -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: t-unit
t-unit:  ## 🧪 Run unit tests only
	@uv run pytest -m unit -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-e2e
test-e2e:  ## 🧪 Run E2E tests
	@uv run pytest test/service/e2e -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: t-smoke
t-smoke:  ## 🔍 Run smoke tests (critical API endpoints)
	@uv run pytest -m smoke -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: t-quick
t-quick:  ## ⚡ Run quick tests (unit + smoke)
	@uv run pytest -m "unit or smoke" -v $(filter-out $@,$(MAKECMDGOALS))

.PHONY: test-cdk
test-cdk:  ## 🏗️ Run CDK infrastructure tests (slow, CPU intensive)
	@echo "⚠️  Warning: CDK tests are CPU intensive and may take 1-2 minutes"
	@uv run pytest test/deployment/ -m "cdk" -v $(filter-out $@,$(MAKECMDGOALS))

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
	@docker-compose build
	@docker-compose up -d
	@echo "✅ Stack started!"
	@echo "   🔀 Load Balancer: http://localhost (nginx)"
	@echo "   🌐 API Gateway:   http://localhost:8000"
	@echo "   📚 Ticketing:     http://localhost:8100/docs"
	@echo "   📊 Kafka UI:      http://localhost:8080"
	@echo "   📈 Grafana:       http://localhost:3000"

.PHONY: d-cd
d-cd:  ## 🛑 Stop Docker stack
	@docker-compose down

.PHONY: d-rs
d-rs:  ## 🔄 Restart services
	@docker-compose restart ticketing-service

.PHONY: d-bs
d-bs:  ## 🔨 Rebuild services
	@docker-compose build ticketing-service
	@docker-compose up -d ticketing-service 

# ==============================================================================
# 📈 SERVICE SCALING (Nginx Load Balancer)
# ==============================================================================

.PHONY: scale-ticketing
scale-ticketing:  ## 🎫 Scale ticketing service (usage: make scale-ticketing N=3)
	@if [ -z "$(N)" ]; then \
		echo "Usage: make scale-ticketing N=<count>"; \
		echo "Example: make scale-ticketing N=5"; \
		exit 1; \
	fi
	@echo "📈 Scaling ticketing-service to $(N) instances..."
	@docker-compose up -d --scale ticketing-service=$(N) --no-recreate
	@echo "✅ Done!"
	@docker-compose ps ticketing-service

.PHONY: scale-down
scale-down:  ## 📉 Scale down to 1 instance
	@echo "📉 Scaling down to 1 instance..."
	@docker-compose up -d --scale ticketing-service=1 --no-recreate
	@echo "✅ Scaled down successfully!"

.PHONY: scale-status
scale-status:  ## 📊 Show current scaling status
	@echo "📊 Current service instances:"
	@docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | grep -E "(ticketing-service|nginx)"

.PHONY: dra
dra:  ## 🚀 Complete Docker reset (down → up → migrate → reset-kafka → seed)
	@echo "🚀 ==================== DOCKER COMPLETE RESET ===================="
	@echo "⚠️  This will stop containers and remove volumes"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@docker-compose down -v
	@docker-compose up -d
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
	@echo "✅ ==================== RESET COMPLETED ===================="

.PHONY: dm
dm:  ## 🗄️ Initialize ScyllaDB schema in Docker
	@echo "🗄️  Initializing ScyllaDB schema..."
	@docker exec -i scylladb1 cqlsh -u cassandra -p cassandra < src/platform/database/scylla_schemas.cql
	@echo "✅ Schema initialization completed"

.PHONY: ds
ds:  ## 🌱 Seed data in Docker
	@docker-compose exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/seed_data.py"

.PHONY: drk
drk:  ## 🌊 Reset Kafka in Docker
	@echo "🌊 Resetting Kafka..."
	@docker-compose exec ticketing-service sh -c "PYTHONPATH=/app uv run python script/reset_kafka.py"
	@echo "✅ Kafka reset completed"

.PHONY: tdt
tdt:  ## 🧪 Run tests in Docker (excludes E2E, deployment, infra, skipped features)
	@docker-compose exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/deployment \
		--ignore=test/infrastructure \
		--ignore=test/service/ticketing/integration/features/booking_insufficient_seats.feature \
		-v -n3

.PHONY: tde2e
tde2e:  ## 🧪 Run E2E tests in Docker
	@docker-compose exec ticketing-service uv run pytest test/service/e2e -v

.PHONY: tdinfra
tdinfra:  ## 🏗️ Run infrastructure tests in Docker
	@echo "🏗️  Testing infrastructure components in Docker..."
	@docker-compose exec ticketing-service uv run pytest test/infrastructure/ -v --tb=short
	@echo "✅ Infrastructure tests complete!"

.PHONY: tdci
tdci:  ## 🤖 Run CI tests (exclude infra, api, e2e, deployment)
	@docker-compose exec ticketing-service uv run pytest test/ \
		--ignore=test/service/e2e \
		--ignore=test/infrastructure \
		--ignore=test/deployment \
		-m "not api and not infra and not e2e" \
		-v

.PHONY: dsh
dsh:  ## 🐚 Shell into Ticketing Service
	@docker-compose exec ticketing-service bash

.PHONY: dal
dal:  ## 📋 View application logs
	@docker-compose logs -f ticketing-service

# ==============================================================================
# ⚡ LOAD TESTING
# ==============================================================================

.PHONY: ltb
ltb:  ## 🔨 Build Go load test binary
	@cd script/go_client && go build -o loadtest main.go

.PHONY: ltt
ltt:  ## 🧪 Tiny load test (10 requests, 10 workers, 10 clients)
	@cd script/go_client && ./loadtest -requests 10 -concurrency 5 -clients 5

.PHONY: lts
lts:  ## 🧪 Small load test (10 requests, 10 workers, 10 clients)
	@cd script/go_client && ./loadtest -requests 50 -concurrency 5 -clients 5

.PHONY: ltm
ltm:  ## ⚡ Medium load test (2 processes × 250 requests, 25 workers each)
	@cd script/go_client && \
		./loadtest -requests 1000 -concurrency 25 -clients 25 & \

.PHONY: ltl
ltl:  ## ⚡ Large load test (2 processes × 250 requests, 25 workers each)
	@cd script/go_client && \
		./loadtest -requests 10000 -concurrency 50 -clients 50 & \

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
# 🌩️ AWS CDK DEPLOYMENT
# ==============================================================================

.PHONY: cdk-synth
cdk-synth:  ## 🔍 Synthesize CDK stack (validate infrastructure code)
	@echo "🔍 Synthesizing CDK stack..."
	@CDK_DEFAULT_ACCOUNT=123456789012 \
		CDK_DEFAULT_REGION=us-west-2 \
		uv run cdk synth --no-lookups
	@echo "✅ CDK synthesis completed!"

.PHONY: cdk-diff
cdk-diff:  ## 📊 Show differences between deployed and local stack
	@echo "📊 Comparing stack differences..."
	@CDK_DEFAULT_ACCOUNT=123456789012 \
		CDK_DEFAULT_REGION=us-west-2 \
		uv run cdk diff

.PHONY: deploy
deploy:  ## 🚀 One-click deployment (infrastructure + Docker images + health check)
	@echo "🚀 Starting one-click deployment..."
	@./deployment/deploy-all.sh

.PHONY: destroy
destroy:  ## 💣 One-click shutdown (delete all AWS resources to stop billing)
	@echo "💣 Starting one-click shutdown..."
	@./deployment/destroy-all.sh

.PHONY: cdk-deploy-dev
cdk-deploy-dev:  ## 🏗️ Deploy CDK infrastructure only (no Docker images)
	@echo "🚀 Deploying to AWS development environment..."
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@uv run cdk deploy --all --require-approval never
	@echo "✅ Deployment completed!"

.PHONY: cdk-deploy-loadtest
cdk-deploy-loadtest:  ## 🧪 Deploy loadtest stack only (Fargate Spot 32GB)
	@echo "🧪 Deploying loadtest infrastructure..."
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@uv run cdk deploy TicketingLoadTestStack --require-approval never
	@echo "✅ Loadtest stack deployed!"
	@echo "📋 Next: Use ECS Console or AWS CLI to run tasks"

.PHONY: cdk-destroy
cdk-destroy:  ## 🗑️ Destroy CDK stacks only (use 'make destroy' for complete cleanup)
	@echo "⚠️  WARNING: This will destroy all AWS resources!"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@uv run cdk destroy --all
	@echo "✅ All stacks destroyed"

.PHONY: cdk-ls
cdk-ls:  ## 📋 List all CDK stacks
	@CDK_DEFAULT_ACCOUNT=123456789012 \
		CDK_DEFAULT_REGION=us-west-2 \
		uv run cdk list

# ==============================================================================
# 📊 MONITORING
# ==============================================================================

.PHONY: monitor mon
monitor mon:  ## 📊 Monitor all ECS services (ticketing, kvrocks)
	@echo "📊 Monitoring all ECS services..."
	@./script/monitor/all_services.sh

.PHONY: monitor-service mons
monitor-service mons:  ## 📊 Monitor single ECS service (usage: make monitor-service SERVICE=ticketing-service)
	@SERVICE=${SERVICE:-ticketing-service}; \
	echo "📊 Monitoring ECS service: $$SERVICE"; \
	./script/monitor/ecs_realtime.sh ticketing-cluster $$SERVICE


# ==============================================================================
# 🐳 AWS ECR (Elastic Container Registry)
# ==============================================================================

.PHONY: ecr-push-all
ecr-push-all:  ## 🚀 Build and push all services to ECR (production)
	@echo "🚀 Building and pushing all services to ECR (production)..."
	@./deployment/script/ecr-push.sh production all

.PHONY: ecr-push-ticketing
ecr-push-ticketing:  ## 🎫 Build and push ticketing service to ECR (production)
	@echo "🎫 Building and pushing ticketing-service to ECR (production)..."
	@./deployment/script/ecr-push.sh production ticketing


.PHONY: ecr-push-staging
ecr-push-staging:  ## 🧪 Build and push all services to ECR (staging)
	@echo "🧪 Building and pushing all services to ECR (staging)..."
	@./deployment/script/ecr-push.sh staging all

.PHONY: ecr-push-dev
ecr-push-dev:  ## 🔧 Build and push all services to ECR (development)
	@echo "🔧 Building and pushing all services to ECR (development)..."
	@./deployment/script/ecr-push.sh development all

.PHONY: ecr-login
ecr-login:  ## 🔐 Login to AWS ECR
	@echo "🔐 Logging in to AWS ECR..."
	@aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
	@echo "✅ ECR login successful"

.PHONY: ecr-list
ecr-list:  ## 📋 List Docker images in ECR repositories
	@echo "📋 Images in ticketing-service repository:"
	@aws ecr list-images --repository-name ticketing-service --region $(AWS_REGION) --output table || echo "Repository not found"

.PHONY: ecr-cleanup
ecr-cleanup:  ## 🧹 Remove old ECR images (keep last 10 per environment)
	@echo "🧹 Cleaning up old ECR images..."
	@echo "⚠️  This will keep only the last 10 images per environment tag"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo "Cleaning ticketing-service..."
	@aws ecr list-images --repository-name ticketing-service --region $(AWS_REGION) \
		--query 'imageIds[?type(imageTag)!=`null`]|sort_by(@, &imageTag)|[0:-10].[imageDigest]' \
		--output text | xargs -I {} aws ecr batch-delete-image \
		--repository-name ticketing-service --region $(AWS_REGION) --image-ids imageDigest={} || true
	@echo "✅ Cleanup completed"

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
	@echo "  dsu/dsd/dsr/dr/dra/dm/drk/ds/dt/de2e/dsh/dal"
	@echo ""
	@echo "🗄️  DATABASE (ScyllaDB)"
	@echo "  db-reset, db-init, cqlsh"
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
