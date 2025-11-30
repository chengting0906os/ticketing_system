# ==============================================================================
# ☁️ AWS OPERATIONS MAKEFILE
# ==============================================================================
# This Makefile contains all AWS-related operations including:
# - AWS Load Testing
# - AWS CDK Deployment
# - AWS ECR (Elastic Container Registry)
# - AWS ECS Service Management
# - AWS Kvrocks Management
#
# Usage: make -f deployment/Makefile <target>
# Or from root: make aws-<command> (delegated from root Makefile)
# ==============================================================================

# AWS Configuration
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "123456789012")
DEPLOY_ENV ?= development

# ==============================================================================
# ☁️ AWS LOAD TESTING (Cloud Environment)
# ==============================================================================

# AWS Concurrent Load Test (Pressure Testing on AWS ALB)
.PHONY: aws-go-clt-t aws-go-clt-s aws-go-clt-m aws-go-clt-l aws-go-clt-f

aws-go-clt-t:  ## 🧪 AWS Concurrent Load Test - Tiny (10 requests, 5 concurrency, 5 clients)
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	echo "🎯 Target: http://$$ALB_DNS"; \
	cd script/go_client && ./concurrent_loadtest -requests 10 -concurrency 5 -clients 5 -host http://$$ALB_DNS

aws-go-clt-s:  ## 🧪 AWS Concurrent Load Test - Small (100 requests, 10 concurrency, 10 clients)
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	echo "🎯 Target: http://$$ALB_DNS"; \
	cd script/go_client && ./concurrent_loadtest -requests 100 -concurrency 10 -clients 10 -host http://$$ALB_DNS

aws-go-clt-m:  ## ⚡ AWS Concurrent Load Test - Medium (5000 requests, 25 concurrency, 25 clients)
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	echo "🎯 Target: http://$$ALB_DNS"; \
	cd script/go_client && ./concurrent_loadtest -requests 5000 -concurrency 25 -clients 25 -host http://$$ALB_DNS

aws-go-clt-l:  ## ⚡ AWS Concurrent Load Test - Large (10000 requests, 50 concurrency, 50 clients)
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	echo "🎯 Target: http://$$ALB_DNS"; \
	cd script/go_client && ./concurrent_loadtest -requests 10000 -concurrency 50 -clients 50 -host http://$$ALB_DNS

aws-go-clt-f:  ## 💪 AWS Concurrent Load Test - Full (50000 requests, 100 concurrency, 100 clients)
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	echo "🎯 Target: http://$$ALB_DNS"; \
	cd script/go_client && ./concurrent_loadtest -requests 50000 -concurrency 100 -clients 100 -host http://$$ALB_DNS

# AWS Reserved Load Test (Sellout Testing on AWS)
.PHONY: aws-go-rlt aws-go-rlt-500 aws-go-rlt-5k aws-go-rlt-25k aws-go-rlt-50k

aws-go-rlt:  ## 🔥 AWS Reserved Load Test - Buys all seats (auto-detects DEPLOY_ENV)
	@$(MAKE) -C script/go_client build-reserved
	@echo "🔥 Running AWS reserved load test (Go)..."
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	echo "🎯 Target: http://$$ALB_DNS"; \
	if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "📊 Production mode: 50,000 seats (100 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env production -event 1 -workers 100 -host http://$$ALB_DNS; \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "📊 Staging mode: 25,000 seats (75 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env staging -event 1 -workers 75 -host http://$$ALB_DNS; \
	elif [ "$(DEPLOY_ENV)" = "development" ]; then \
		echo "📊 Development mode: 5,000 seats (50 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env development -event 1 -workers 50 -host http://$$ALB_DNS; \
	else \
		echo "📊 Local dev mode: 500 seats (20 workers, random 1-4 per booking)"; \
		cd script/go_client && ./reserved_loadtest -env development -event 1 -workers 20 -host http://$$ALB_DNS; \
	fi

aws-go-rlt-500:  ## 🔥 AWS Reserved Load Test - 500 seats (local_dev: 20 workers)
	@$(MAKE) -f deployment/Makefile aws-go-rlt DEPLOY_ENV=development

aws-go-rlt-5k:  ## 🔥 AWS Reserved Load Test - 5,000 seats (development: 50 workers)
	@$(MAKE) -f deployment/Makefile aws-go-rlt DEPLOY_ENV=staging

aws-go-rlt-50k:  ## 🔥 AWS Reserved Load Test - 50,000 seats (production: 100 workers)
	@$(MAKE) -f deployment/Makefile aws-go-rlt DEPLOY_ENV=production

# AWS Full Reserved Load Test (1 ticket per worker, deterministic)
.PHONY: aws-go-frlt aws-go-frlt-1k aws-go-frlt-2k aws-go-frlt-5k aws-go-frlt-50k

aws-go-frlt:  ## 🚀 AWS Full Reserved Load Test - Buys all seats (1 ticket per worker, configurable WORKERS/BATCH)
	@$(MAKE) -C script/go_client build-full-reserved
	@echo "🚀 Running AWS FULL reserved load test (Go)..."
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	WORKERS=$${WORKERS:-100}; \
	BATCH=$${BATCH:-1}; \
	echo "🎯 Target: http://$$ALB_DNS"; \
	echo "📊 Workers: $$WORKERS, Batch: $$BATCH"; \
	if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "📊 Production mode: 50,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env production -event 1 -workers $$WORKERS -batch $$BATCH -host http://$$ALB_DNS; \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "📊 Staging mode: 5,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env staging -event 1 -workers $$WORKERS -batch $$BATCH -host http://$$ALB_DNS; \
	elif [ "$(DEPLOY_ENV)" = "local_dev_2k" ]; then \
		echo "📊 Local Dev 2k mode: 2,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env local_dev_2k -event 1 -workers $$WORKERS -batch $$BATCH -host http://$$ALB_DNS; \
	elif [ "$(DEPLOY_ENV)" = "local_dev_1000" ]; then \
		echo "📊 Local Dev 1000 mode: 1,000 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env local_dev_1000 -event 1 -workers $$WORKERS -batch $$BATCH -host http://$$ALB_DNS; \
	else \
		echo "📊 Development mode: 500 seats"; \
		cd script/go_client && ./full_reserved_loadtest -env development -event 1 -workers $$WORKERS -batch $$BATCH -host http://$$ALB_DNS; \
	fi

aws-go-frlt-1k:  ## 🚀 AWS Full Reserved Load Test - 1,000 seats (local_dev_1000)
	@$(MAKE) -f deployment/Makefile aws-go-frlt DEPLOY_ENV=local_dev_1000

aws-go-frlt-2k:  ## 🚀 AWS Full Reserved Load Test - 2,000 seats (local_dev_2k)
	@$(MAKE) -f deployment/Makefile aws-go-frlt DEPLOY_ENV=local_dev_2k

aws-go-frlt-5k:  ## 🚀 AWS Full Reserved Load Test - 5,000 seats (staging)
	@$(MAKE) -f deployment/Makefile aws-go-frlt DEPLOY_ENV=staging

aws-go-frlt-50k:  ## 🚀 AWS Full Reserved Load Test - 50,000 seats (production)
	@$(MAKE) -f deployment/Makefile aws-go-frlt DEPLOY_ENV=production

# AWS Reserved Load Test via ECS Task (runs inside AWS, much faster)
.PHONY: aws-rlt-ecs aws-rlt-ecs-500 aws-rlt-ecs-5k  aws-rlt-ecs-50k

aws-rlt-ecs: ecr-push-loadtest  ## 🚀 AWS Reserved Load Test via LoadTest ECS Task (fast, runs inside AWS)
	@echo "🚀 Running reserved load test via LoadTest ECS Task (inside AWS)..."
	@ALB_DNS=$$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?LoadBalancerName==`ticketing-alb`].DNSName' --output text); \
	SUBNET=$$(aws ec2 describe-subnets \
		--filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" \
		--query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups \
		--filters "Name=group-name,Values=*LoadTestSG*" \
		--query 'SecurityGroups[0].GroupId' --output text); \
	if [ -z "$$SG" ] || [ "$$SG" = "None" ]; then \
		echo "⚠️  LoadTestSG not found, using AuroraSecurityGroup"; \
		SG=$$(aws ec2 describe-security-groups \
			--filters "Name=group-name,Values=*AuroraSecurityGroup*" \
			--query 'SecurityGroups[0].GroupId' --output text); \
	fi; \
	if [ "$(DEPLOY_ENV)" = "production" ]; then \
		echo "📊 Production mode: 50,000 seats (100 workers)"; \
		WORKERS=100; ENV_NAME=production; \
	elif [ "$(DEPLOY_ENV)" = "staging" ]; then \
		echo "📊 Staging mode: 25,000 seats (75 workers)"; \
		WORKERS=75; ENV_NAME=staging; \
	elif [ "$(DEPLOY_ENV)" = "development" ]; then \
		echo "📊 Development mode: 5,000 seats (50 workers)"; \
		WORKERS=50; ENV_NAME=development; \
	else \
		echo "📊 Local dev mode: 500 seats (20 workers)"; \
		WORKERS=20; ENV_NAME=local_dev; \
	fi; \
	echo "🎯 Target: http://$$ALB_DNS"; \
	echo "📡 Launching LoadTest task (family: loadtest-runner)..."; \
	TASK_ARN=$$(aws ecs run-task \
		--cluster ticketing-cluster \
		--task-definition loadtest-runner \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--overrides "{\"containerOverrides\":[{\"name\":\"loadtest\",\"command\":[\"sh\",\"-c\",\"cd script/go_client && ./reserved_loadtest -env $$ENV_NAME -event 1 -workers $$WORKERS -host http://$$ALB_DNS\"]}]}" \
		--query 'tasks[0].taskArn' --output text); \
	echo "✅ Task started: $$TASK_ARN"; \
	echo "⏳ Waiting for task to complete..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --tasks $$TASK_ARN; \
	echo "📊 Fetching results..."; \
	TASK_ID=$$(echo $$TASK_ARN | rev | cut -d'/' -f1 | rev); \
	aws logs get-log-events \
		--log-group-name /ecs/loadtest-runner \
		--log-stream-name loadtest/loadtest/$$TASK_ID \
		--query 'events[*].message' --output text

aws-rlt-ecs-500:  ## 🚀 Fast Reserved Load Test - 500 seats (via ECS, 20 workers)
	@$(MAKE) -f deployment/Makefile aws-rlt-ecs DEPLOY_ENV=local_dev

aws-rlt-ecs-5k:  ## 🚀 Fast Reserved Load Test - 5,000 seats (via ECS, 50 workers)
	@$(MAKE) -f deployment/Makefile aws-rlt-ecs DEPLOY_ENV=development

aws-rlt-ecs-25k:  ## 🚀 Fast Reserved Load Test - 25,000 seats (via ECS, 75 workers)
	@$(MAKE) -f deployment/Makefile aws-rlt-ecs DEPLOY_ENV=staging

aws-rlt-ecs-50k:  ## 🚀 Fast Reserved Load Test - 50,000 seats (via ECS, 100 workers)
	@$(MAKE) -f deployment/Makefile aws-rlt-ecs DEPLOY_ENV=production

# AWS Load Test with Seed (Complete workflow)
.PHONY: aws-loadtest-full

aws-loadtest-full:  ## 🚀 AWS Complete Load Test (seed → reserved sellout test)
	@echo "🚀 ==================== AWS COMPLETE LOAD TEST ===================="
	@echo "📋 This will:"
	@echo "   1. Seed initial data (users + event)"
	@echo "   2. Run reserved load test (sellout scenario)"
	@echo ""
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "🌱 Step 1/2: Seeding data..."
	@$(MAKE) -f deployment/Makefile aws-seed
	@echo ""
	@echo "⏳ Waiting 10s for seed task to complete..."
	@sleep 10
	@echo ""
	@echo "🔥 Step 2/2: Running reserved load test..."
	@$(MAKE) -f deployment/Makefile aws-go-rlt
	@echo ""
	@echo "✅ ==================== LOAD TEST COMPLETE ===================="

# AWS LoadTest Task Management (Interactive Operations)
.PHONY: aws-loadtest-run aws-loadtest-exec aws-loadtest-stop aws-loadtest-status aws-loadtest-logs

aws-loadtest-run:  ## 🚀 Start LoadTest task (sleep infinity, for ECS Exec)
	@echo "🚀 Starting LoadTest task..."
	@SUBNET=$$(aws ec2 describe-subnets \
		--filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" \
		--query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups \
		--filters "Name=group-name,Values=*LoadTestSG*" \
		--query 'SecurityGroups[0].GroupId' --output text); \
	TASK_ARN=$$(aws ecs run-task \
		--cluster ticketing-cluster \
		--task-definition loadtest-runner \
		--launch-type FARGATE \
		--enable-execute-command \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--query 'tasks[0].taskArn' --output text); \
	echo "✅ LoadTest task started: $$TASK_ARN"; \
	echo "⏳ Waiting for task to be running (45s)..."; \
	sleep 45; \
	echo "💡 Connect to task: make aws-loadtest-exec"

aws-loadtest-exec:  ## 🔧 Exec into running LoadTest task (interactive shell)
	@echo "🔧 Connecting to LoadTest task..."
	@TASK_ARN=$$(aws ecs list-tasks \
		--cluster ticketing-cluster \
		--family loadtest-runner \
		--desired-status RUNNING \
		--query 'taskArns[0]' --output text); \
	if [ "$$TASK_ARN" = "None" ] || [ -z "$$TASK_ARN" ]; then \
		echo "❌ No running LoadTest task found"; \
		echo "💡 Start one with: make aws-loadtest-run"; \
		exit 1; \
	fi; \
	echo "📡 Task: $$TASK_ARN"; \
	echo ""; \
	echo "🎯 Once inside, you can run:"; \
	echo ""; \
	echo "  🐍 Python Commands (re-seed, reset):"; \
	echo "    cd /app"; \
	echo "    DEPLOY_ENV=development uv run python -m script.seed_data        # Seed data"; \
	echo "    uv run python -m script.reset_database                          # Reset DB + Kvrocks"; \
	echo ""; \
	echo "  📊 Go Load Testing (already in /app/script/go_client):"; \
	echo "    # Using Make commands:"; \
	echo "    make rlt                                    # Reserved (100 workers, random 1-4 tickets)"; \
	echo "    make frlt WORKERS=500 BATCH=1               # Full reserved (500 workers, 1 ticket each)"; \
	echo "    make clt-medium                             # Concurrent (500 req, 25 concurrency)"; \
	echo ""; \
	echo "    # Direct binary execution:"; \
	echo "    ./reserved_loadtest -env development -event 1 -workers 100"; \
	echo "    ./full_reserved_loadtest -env development -event 1 -workers 500 -batch 1"; \
	echo "    ./concurrent_loadtest -requests 500 -concurrency 25 -clients 25"; \
	echo ""; \
	aws ecs execute-command \
		--cluster ticketing-cluster \
		--task $$TASK_ARN \
		--container loadtest \
		--interactive \
		--command "/bin/sh"

aws-loadtest-stop:  ## 🛑 Stop all running LoadTest tasks
	@echo "🛑 Stopping all LoadTest tasks..."
	@TASK_ARNS=$$(aws ecs list-tasks \
		--cluster ticketing-cluster \
		--family loadtest-runner \
		--desired-status RUNNING \
		--query 'taskArns[]' --output text); \
	if [ -z "$$TASK_ARNS" ]; then \
		echo "✅ No running LoadTest tasks"; \
	else \
		for task in $$TASK_ARNS; do \
			echo "Stopping $$task"; \
			aws ecs stop-task --cluster ticketing-cluster --task $$task --query 'task.taskArn' --output text; \
		done; \
		echo "✅ All LoadTest tasks stopped"; \
	fi

aws-loadtest-status:  ## 📊 Show LoadTest task status
	@echo "📊 LoadTest Task Status:"
	@aws ecs list-tasks \
		--cluster ticketing-cluster \
		--family loadtest-runner \
		--query 'taskArns[]' --output text | \
	while read task; do \
		if [ -n "$$task" ]; then \
			aws ecs describe-tasks --cluster ticketing-cluster --tasks $$task \
				--query 'tasks[0].{TaskArn:taskArn,Status:lastStatus,StartedAt:startedAt,CPU:cpu,Memory:memory}' \
				--output table; \
		fi; \
	done || echo "No LoadTest tasks found"

aws-loadtest-logs:  ## 🔍 Tail logs from LoadTest task
	@echo "🔍 Tailing LoadTest logs (Ctrl+C to exit)..."
	@aws logs tail /ecs/loadtest-runner --follow --format short

# ==============================================================================
# 🖥️  EC2 LOADTEST (ARM64, always running)
# ==============================================================================

.PHONY: aws-lt-exec aws-lt-status aws-lt-start aws-lt-stop

aws-lt-exec:  ## 🔧 Connect to EC2 LoadTest instance (SSM Session Manager)
	@echo "🔧 Connecting to EC2 LoadTest instance..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=LoadTest-Instance" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "❌ No running LoadTest instance found"; \
		echo "💡 Check status with: make aws-lt-status"; \
		exit 1; \
	fi; \
	echo "📡 Instance: $$INSTANCE_ID"; \
	echo ""; \
	echo "🎯 You can run:"; \
	echo "   cd /app/script/go_client"; \
	echo "   ./reserved_loadtest -env development -event 1 -workers 20 -host http://ALB_DNS"; \
	echo ""; \
	aws ssm start-session --target $$INSTANCE_ID

aws-lt-status:  ## 📊 Show EC2 LoadTest instance status
	@echo "📊 EC2 LoadTest Instance Status:"
	@aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=LoadTest-Instance" \
		--query 'Reservations[0].Instances[0].{InstanceId:InstanceId,State:State.Name,Type:InstanceType,PrivateIP:PrivateIpAddress,LaunchTime:LaunchTime}' \
		--output table

aws-lt-start:  ## 🚀 Start EC2 LoadTest instance
	@echo "🚀 Starting EC2 LoadTest instance..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=LoadTest-Instance" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "❌ LoadTest instance not found"; \
		exit 1; \
	fi; \
	aws ec2 start-instances --instance-ids $$INSTANCE_ID; \
	echo "✅ Instance starting: $$INSTANCE_ID"; \
	echo "⏳ Wait 1-2 minutes before connecting"

aws-lt-stop:  ## 🛑 Stop EC2 LoadTest instance (cost saving)
	@echo "🛑 Stopping EC2 LoadTest instance..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=LoadTest-Instance" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "✅ No running LoadTest instance"; \
		exit 0; \
	fi; \
	aws ec2 stop-instances --instance-ids $$INSTANCE_ID; \
	echo "✅ Instance stopped: $$INSTANCE_ID"

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
	@echo "  - development: max_acu = 8 (minimal)"
	@echo "  - staging:     max_acu = 32 (moderate)"
	@echo "  - production:  max_acu = 64 (full scale)"
	@echo ""
	@echo "💡 Use 'make dev-deploy-all', 'make staging-deploy-all', or 'make prod-deploy-all' to deploy"

dev-deploy-full:  ## 🎯 Build + Push + Deploy (DEVELOPMENT: complete from scratch)
	@echo "🎯 Starting complete deployment process..."
	@echo "📦 Step 1/2: Building and pushing Docker images to ECR"
	@echo ""
	@./deployment/script/ecr-push.sh development all
	@echo ""
	@echo "🚀 Step 2/2: Deploying CDK stacks"
	@echo ""
	@DEPLOY_ENV=development uv run cdk deploy --all --require-approval never
	@echo ""
	@echo "✅ Complete deployment finished!"
	@echo "💡 Next steps:"
	@echo "   - Run 'make aws-restart-services' to restart ECS with latest images"
	@echo "   - Run 'make aws-reset' to migrate DB + seed data + reset Kafka"
	@echo "   - Run 'make aws-status' to check service status"

dev-redeploy-skip-aurora:  ## 🔄 Rebuild all stacks EXCEPT Aurora & Kvrocks (saves 10+ min)
	@echo "🔄 Rebuilding stacks (preserving Aurora & Kvrocks)..."
	@echo "⚠️  This will delete and recreate:"
	@echo "   - Kafka Stack (t4g.medium ARM)"
	@echo "   - API Service"
	@echo "   - Consumer Services"
	@echo "   - LoadTest Stack"
	@echo ""
	@echo "✅ This will preserve:"
	@echo "   - Aurora Database (all data preserved)"
	@echo "   - Kvrocks Instance (m6id.large NVMe)"
	@echo ""
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "❌ Cancelled" && exit 1)
	@echo ""
	@echo "🗑️  Step 1/4: Deleting dependent stacks..."
	@DEPLOY_ENV=development uv run cdk destroy LoadTestStack --force || true
	@DEPLOY_ENV=development uv run cdk destroy ReservationConsumerStack --force || true
	@DEPLOY_ENV=development uv run cdk destroy TicketingConsumerStack --force || true
	@DEPLOY_ENV=development uv run cdk destroy APIServiceStack --force || true
	@DEPLOY_ENV=development uv run cdk destroy TicketingKafkaStack --force || true
	@echo ""
	@echo "📦 Step 2/4: Building and pushing Docker images to ECR"
	@./deployment/script/ecr-push.sh development all
	@echo ""
	@echo "🚀 Step 3/4: Deploying all stacks"
	@DEPLOY_ENV=development uv run cdk deploy --all --require-approval never
	@echo ""
	@echo "⏳ Step 4/4: Waiting for services to start (2 min)..."
	@sleep 120
	@echo ""
	@echo "✅ Rebuild complete! Aurora & Kvrocks data preserved."
	@echo "💡 Next steps:"
	@echo "   - Run 'make aws-status' to check service status"
	@echo "   - Run 'make aws-reset-kafka' to reset Kafka topics"
	@echo "   - Run 'make aws-reset-kvrocks' to flush Kvrocks data"

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

staging-deploy-all:  ## 🧪 Deploy all stacks (STAGING environment: Aurora 2-32 ACU)
	@echo "🧪 Deploying to AWS staging environment..."
	@echo "📋 Configuration:"
	@echo "   - Aurora ACU: 2-32 (moderate pre-production)"
	@echo "   - ECS Tasks: 1-3 per service"
	@echo "   - Consumers: 10-50 tasks max (25 vCPU capacity)"
	@echo ""
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@DEPLOY_ENV=staging uv run cdk deploy --all --require-approval never
	@echo "✅ Staging deployment completed!"

prod-deploy-all:  ## 🚀 Deploy all stacks (PRODUCTION environment: Aurora 4-64 ACU)
	@echo "🚀 Deploying to AWS production environment..."
	@echo "📋 Configuration:"
	@echo "   - Aurora ACU: 4-64 (auto-scaling for 10K TPS)"
	@echo "   - ECS Tasks: 1-4 per service"
	@echo "   - Consumers: 50-200 tasks max (100 vCPU capacity)"
	@echo ""
	@echo "⚠️  WARNING: Production configuration uses higher resources!"
	@echo "⚠️  Make sure AWS credentials are configured (aws configure)"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@DEPLOY_ENV=production uv run cdk deploy --all --require-approval never
	@echo "✅ Production deployment completed!"

staging-deploy-full:  ## 🎯 Build + Push + Deploy (STAGING: complete from scratch)
	@echo "🎯 Starting complete STAGING deployment process..."
	@echo "⚠️  This will deploy to STAGING environment!"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "📦 Step 1/2: Building and pushing Docker images to ECR"
	@echo ""
	@./deployment/script/ecr-push.sh staging all
	@echo ""
	@echo "🚀 Step 2/2: Deploying CDK stacks"
	@echo ""
	@DEPLOY_ENV=staging uv run cdk deploy --all --require-approval never
	@echo ""
	@echo "✅ Complete STAGING deployment finished!"
	@echo "💡 Next steps:"
	@echo "   - Run 'DEPLOY_ENV=staging make aws-reset' to migrate DB + seed data"
	@echo "   - Run 'make aws-status' to check service status"

prod-deploy-full:  ## 🎯 Build + Push + Deploy (PRODUCTION: complete from scratch)
	@echo "🎯 Starting complete PRODUCTION deployment process..."
	@echo "⚠️  WARNING: This will deploy to PRODUCTION environment!"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "📦 Step 1/2: Building and pushing Docker images to ECR"
	@echo ""
	@./deployment/script/ecr-push.sh production all
	@echo ""
	@echo "🚀 Step 2/2: Deploying CDK stacks"
	@echo ""
	@DEPLOY_ENV=production uv run cdk deploy --all --require-approval never
	@echo ""
	@echo "✅ Complete PRODUCTION deployment finished!"
	@echo "💡 Next steps:"
	@echo "   - Run 'DEPLOY_ENV=production make aws-reset' to migrate DB + seed data"
	@echo "   - Run 'make aws-status' to check service status"

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
	@echo "🪑 Building and pushing reservation-service to ECR (production)..."
	@./deployment/script/ecr-push.sh production seat-reservation

ecr-push-loadtest:  ## 🧪 Build and push loadtest (Go + Python) to ECR
	@echo "🧪 Building and pushing loadtest (Go + Python) to ECR..."
	@AWS_ACCOUNT_ID=$(AWS_ACCOUNT_ID); \
	AWS_REGION=$(AWS_REGION); \
	aws ecr get-login-password --region $$AWS_REGION | docker login --username AWS --password-stdin $$AWS_ACCOUNT_ID.dkr.ecr.$$AWS_REGION.amazonaws.com; \
	cd .. && docker build --platform linux/amd64 -t $$AWS_ACCOUNT_ID.dkr.ecr.$$AWS_REGION.amazonaws.com/ticketing-loadtest:latest -f script/go_client/Dockerfile . && \
	docker push $$AWS_ACCOUNT_ID.dkr.ecr.$$AWS_REGION.amazonaws.com/ticketing-loadtest:latest && \
	echo "✅ Loadtest (Go + Python) pushed to ECR"

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
	@echo "📋 Images in reservation-service repository:"
	@aws ecr list-images --repository-name reservation-service --region $(AWS_REGION) --output table || echo "Repository not found"

ecr-cleanup:  ## 🧹 Remove old ECR images (keep last 10 per environment)
	@echo "🧹 Cleaning up old ECR images..."
	@echo "⚠️  This will keep only the last 10 images per environment tag"
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@for repo in ticketing-service reservation-service; do \
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

.PHONY: aws-restart-services aws-reset aws-reset-db aws-migrate aws-reset-kafka aws-reset-kvrocks aws-seed aws-stop aws-start aws-status aws-logs aws-logs-ticketing aws-logs-reservation aws-db-list aws-db-schema aws-db-migrations aws-db-query aws-api-exec aws-help

aws-restart-services:  ## 🔄 Restart all ECS services (force new deployment to pull latest images)
	@echo "🔄 Restarting all ECS services to pull latest images..."
	@echo ""
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-ticketing-service --force-new-deployment \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-booking-service --force-new-deployment \
		--query 'service.serviceName' --output text
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-reservation-service --force-new-deployment \
		--query 'service.serviceName' --output text
	@echo "✅ All services deployment triggered"
	@echo ""
	@echo "⏳ Waiting for services to be stable (this may take 2-3 minutes)..."
	@aws ecs wait services-stable --cluster ticketing-cluster \
		--services ticketing-development-ticketing-service \
			ticketing-development-booking-service \
			ticketing-development-reservation-service
	@echo "✅ All services are stable and running with latest images"
	@echo ""
	@echo "💡 Check status: make aws-status"


aws-migrate:  ## 🗄️ Run migrations on AWS Aurora (via ECS task)
	@echo "🗄️  Running database migrations..."
	@TASK_DEF=$$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-ticketing-service --region us-west-2 --query 'services[0].taskDefinition' --output text); \
	TASK_ARN=$$(aws ecs run-task \
		--cluster ticketing-cluster \
		--task-definition $$TASK_DEF \
		--launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$(shell aws ec2 describe-subnets --filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" --query 'Subnets[0].SubnetId' --output text)],securityGroups=[$(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=*AuroraSecurityGroup*" --query 'SecurityGroups[0].GroupId' --output text)]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["uv","run","alembic","-c","alembic.ini","upgrade","head"]}]}' \
		--query 'tasks[0].taskArn' --output text); \
	echo "   Task ARN: $$TASK_ARN"; \
	echo "   ⏳ Waiting for task to complete..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --tasks $$TASK_ARN; \
	EXIT_CODE=$$(aws ecs describe-tasks --cluster ticketing-cluster --tasks $$TASK_ARN --query 'tasks[0].containers[0].exitCode' --output text); \
	if [ "$$EXIT_CODE" = "0" ]; then \
		echo "   ✅ Migration completed successfully"; \
	else \
		echo "   ❌ Migration failed with exit code: $$EXIT_CODE"; \
		exit 1; \
	fi

aws-reset-kafka:  ## 🌊 Reset Kafka topics on AWS (connect to EC2 and reset)
	@echo "🌊 Resetting Kafka topics..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	COMMAND_ID=$$(aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters 'commands=["cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic ticketing-events || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic seat-reservation-events || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic ticketing-events --partitions 6 --replication-factor 3 || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic seat-reservation-events --partitions 6 --replication-factor 3 || true"]' \
		--query 'Command.CommandId' --output text); \
	echo "   Command ID: $$COMMAND_ID"; \
	echo "   ⏳ Waiting for command to complete..."; \
	aws ssm wait command-executed --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID; \
	STATUS=$$(aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'Status' --output text); \
	if [ "$$STATUS" = "Success" ]; then \
		echo "   ✅ Kafka topics reset successfully"; \
	else \
		echo "   ❌ Kafka reset failed with status: $$STATUS"; \
		exit 1; \
	fi

aws-reset-kvrocks:  ## 🗑️ Flush Kvrocks data on AWS (connect to EC2 and flush)
	@echo "🗑️  Flushing Kvrocks..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "❌ No running Kvrocks instance found"; \
		exit 1; \
	fi; \
	aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters 'commands=["redis-cli -h localhost -p 6666 FLUSHDB"]' \
		--query 'Command.CommandId' --output text
	@echo "✅ Kvrocks flushed"




aws-stop:  ## 🛑 Stop ALL AWS services (ECS + EC2 Kafka + EC2 Kvrocks + LoadTest, keep Aurora only)
	@echo "🛑 Stopping ALL AWS services..."
	@echo "⚠️  This will:"
	@echo "   - Scale all ECS services to 0"
	@echo "   - Stop all LoadTest tasks"
	@echo "   - Stop EC2 Kafka instance"
	@echo "   - Stop EC2 Kvrocks instance"
	@echo "   - Keep Aurora running (minimal cost)"
	@echo ""
	@echo "Continue? (y/N)"
	@read -r confirm && [ "$$confirm" = "y" ] || (echo "Cancelled" && exit 1)
	@echo ""
	@echo "🧪 Stopping LoadTest tasks..."
	@TASK_ARNS=$$(aws ecs list-tasks \
		--cluster ticketing-cluster \
		--family loadtest-runner \
		--desired-status RUNNING \
		--query 'taskArns[]' --output text); \
	if [ -z "$$TASK_ARNS" ]; then \
		echo "✅ No running LoadTest tasks"; \
	else \
		for task in $$TASK_ARNS; do \
			echo "Stopping $$task"; \
			aws ecs stop-task --cluster ticketing-cluster --task $$task --query 'task.taskArn' --output text 2>/dev/null || true; \
		done; \
		echo "✅ All LoadTest tasks stopped"; \
	fi
	@echo ""
	@echo "📦 Scaling ECS services to 0..."
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-ticketing-service --desired-count 0 \
		--query 'service.serviceName' --output text 2>/dev/null || echo "⚠️  ticketing-development-ticketing-service not found"
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-booking-service --desired-count 0 \
		--query 'service.serviceName' --output text 2>/dev/null || echo "⚠️  ticketing-development-booking-service not found"
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-reservation-service --desired-count 0 \
		--query 'service.serviceName' --output text 2>/dev/null || echo "⚠️  ticketing-development-reservation-service not found"
	@echo "✅ ECS services scaled to 0 (where found)"
	@echo ""
	@echo "🔌 Stopping EC2 Kafka instances (all 3 brokers)..."
	@INSTANCE_IDS=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=kafka-broker-*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[*].Instances[*].InstanceId' --output text | tr '\t' ' '); \
	if [ -n "$$INSTANCE_IDS" ] && [ "$$INSTANCE_IDS" != "None" ]; then \
		echo "📦 Found Kafka instances: $$INSTANCE_IDS"; \
		aws ec2 stop-instances --instance-ids $$INSTANCE_IDS --query 'StoppingInstances[*].InstanceId' --output text; \
		echo "✅ EC2 Kafka stopped: $$INSTANCE_IDS"; \
	else \
		echo "⚠️  EC2 Kafka already stopped or not found"; \
	fi
	@echo ""
	@echo "🔌 Stopping EC2 Kvrocks instance (via Auto Scaling Group)..."
	@ASG_NAME=$$(aws autoscaling describe-auto-scaling-groups \
		--query 'AutoScalingGroups[?contains(Tags[?Key==`aws:cloudformation:stack-name`].Value, `TicketingKvrocksStack`)].AutoScalingGroupName' \
		--output text); \
	if [ "$$ASG_NAME" != "None" ] && [ -n "$$ASG_NAME" ]; then \
		echo "📦 Found ASG: $$ASG_NAME"; \
		aws autoscaling update-auto-scaling-group --auto-scaling-group-name $$ASG_NAME --min-size 0; \
		aws autoscaling set-desired-capacity --auto-scaling-group-name $$ASG_NAME --desired-capacity 0; \
		echo "✅ EC2 Kvrocks ASG scaled to 0: $$ASG_NAME"; \
	else \
		echo "⚠️  EC2 Kvrocks ASG not found"; \
	fi
	@echo ""
	@echo "✅ ==================== ALL SERVICES STOPPED ===================="
	@echo "💰 Cost now: ~$0.01/hour (Aurora Serverless v2 at 0.5 ACU minimum)"
	@echo "💡 To restart services: make aws-start"
	@echo "💡 To run LoadTest: make aws-loadtest-run (on-demand)"

aws-start:  ## ▶️  Start ALL AWS services (ECS + EC2 Kafka + EC2 Kvrocks)
	@echo "▶️  Starting ALL AWS services..."
	@echo ""
	@echo "🔌 Starting EC2 Kvrocks instance (via Auto Scaling Group)..."
	@ASG_NAME=$$(aws autoscaling describe-auto-scaling-groups \
		--query 'AutoScalingGroups[?contains(Tags[?Key==`aws:cloudformation:stack-name`].Value, `TicketingKvrocksStack`)].AutoScalingGroupName' \
		--output text); \
	if [ "$$ASG_NAME" != "None" ] && [ -n "$$ASG_NAME" ]; then \
		echo "📦 Found ASG: $$ASG_NAME"; \
		aws autoscaling update-auto-scaling-group --auto-scaling-group-name $$ASG_NAME --min-size 1; \
		aws autoscaling set-desired-capacity --auto-scaling-group-name $$ASG_NAME --desired-capacity 1; \
		echo "✅ EC2 Kvrocks ASG scaled to 1: $$ASG_NAME"; \
		echo "⏳ Waiting 60s for Kvrocks instance to launch and be ready..."; \
		sleep 60; \
	else \
		echo "⚠️  EC2 Kvrocks ASG not found"; \
	fi
	@echo ""
	@echo "🔌 Starting EC2 Kafka instances (all 3 brokers)..."
	@INSTANCE_IDS=$$(aws ec2 describe-instances \
		--filters "Name=tag:Name,Values=kafka-broker-*" "Name=instance-state-name,Values=stopped" \
		--query 'Reservations[*].Instances[*].InstanceId' --output text | tr '\t' ' '); \
	if [ -n "$$INSTANCE_IDS" ] && [ "$$INSTANCE_IDS" != "None" ]; then \
		echo "📦 Found Kafka instances: $$INSTANCE_IDS"; \
		aws ec2 start-instances --instance-ids $$INSTANCE_IDS --query 'StartingInstances[*].InstanceId' --output text; \
		echo "✅ EC2 Kafka starting: $$INSTANCE_IDS"; \
		echo "⏳ Waiting 60s for Kafka cluster to be ready..."; \
		sleep 60; \
	else \
		echo "⚠️  EC2 Kafka already running or not found"; \
	fi
	@echo ""
	@echo "📦 Scaling ECS services back to normal..."
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-ticketing-service --desired-count 1 \
		--query 'service.serviceName' --output text 2>/dev/null || echo "⚠️  ticketing-development-ticketing-service not found"
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-booking-service --desired-count 2 \
		--query 'service.serviceName' --output text 2>/dev/null || echo "⚠️  ticketing-development-booking-service not found"
	@aws ecs update-service --cluster ticketing-cluster \
		--service ticketing-development-reservation-service --desired-count 2 \
		--query 'service.serviceName' --output text 2>/dev/null || echo "⚠️  ticketing-development-reservation-service not found"
	@echo ""
	@echo "✅ ==================== ALL SERVICES STARTED ===================="
	@echo "💡 Check status: make aws-status"

aws-status:  ## 📊 Check status of all AWS ECS services
	@echo "📊 ECS Services Status:"
	@aws ecs describe-services --cluster ticketing-cluster \
		--services ticketing-development-ticketing-service \
		         ticketing-development-booking-service \
		         ticketing-development-reservation-service \
		--query 'services[].[serviceName,status,runningCount,desiredCount]' \
		--output table

aws-logs:  ## 🔍 Tail logs from AWS API service
	@echo "🔍 Tailing API service logs (Ctrl+C to exit)..."
	@LOG_GROUP=$$(aws ecs describe-task-definition \
		--task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-ticketing-service --query 'services[0].taskDefinition' --output text | rev | cut -d'/' -f1 | rev) \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	aws logs tail $$LOG_GROUP --follow --format short

aws-logs-ticketing:  ## 🔍 Tail logs from AWS Ticketing Consumer
	@echo "🔍 Tailing Ticketing Consumer logs (Ctrl+C to exit)..."
	@LOG_GROUP=$$(aws ecs describe-task-definition \
		--task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-booking-service --query 'services[0].taskDefinition' --output text | rev | cut -d'/' -f1 | rev) \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	aws logs tail $$LOG_GROUP --follow --format short

aws-logs-reservation:  ## 🔍 Tail logs from AWS Reservation Consumer
	@echo "🔍 Tailing Reservation Consumer logs (Ctrl+C to exit)..."
	@LOG_GROUP=$$(aws ecs describe-task-definition \
		--task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-reservation-service --query 'services[0].taskDefinition' --output text | rev | cut -d'/' -f1 | rev) \
		--query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text); \
	aws logs tail $$LOG_GROUP --follow --format short

aws-api-exec:  ## 🔧 Exec into running API service task (interactive shell)
	@echo "🔧 Connecting to API service task..."
	@TASK_ARN=$$(aws ecs list-tasks \
		--cluster ticketing-cluster \
		--service-name ticketing-development-ticketing-service \
		--desired-status RUNNING \
		--query 'taskArns[0]' --output text); \
	if [ "$$TASK_ARN" = "None" ] || [ -z "$$TASK_ARN" ]; then \
		echo "❌ No running API service task found"; \
		echo "💡 Check status with: make aws-status"; \
		exit 1; \
	fi; \
	echo "📡 Task: $$TASK_ARN"; \
	echo "🎯 You can now run:"; \
	echo "   - uv run python -m script.reset_database    # Reset database"; \
	echo "   - uv run python -m script.seed_data         # Seed data"; \
	echo ""; \
	aws ecs execute-command \
		--cluster ticketing-cluster \
		--task $$TASK_ARN \
		--container Container \
		--interactive \
		--command "/bin/bash"

aws-db-users:  ## 👥 Quick check: List users in Aurora (fast, via ECS Exec)
	@echo "👥 Checking users in Aurora..."
	@TASK_ARN=$$(aws ecs list-tasks \
		--cluster ticketing-cluster \
		--service-name ticketing-development-ticketing-service \
		--desired-status RUNNING \
		--query 'taskArns[0]' --output text); \
	if [ "$$TASK_ARN" = "None" ] || [ -z "$$TASK_ARN" ]; then \
		echo "❌ No running API service task found"; \
		exit 1; \
	fi; \
	echo "📡 Executing query on task: $$TASK_ARN"; \
	aws ecs execute-command \
		--cluster ticketing-cluster \
		--task $$TASK_ARN \
		--container Container \
		--interactive \
		--command "sh -c 'PYTHONPATH=/app uv run python deployment/script/quick_db_check.py'"

aws-db-list:  ## 🗄️ List all Aurora tables with row counts (via ECS task)
	@echo "🗄️  Listing Aurora tables..."
	@TASK_DEF=$$(aws ecs describe-services \
		--cluster ticketing-cluster \
		--services ticketing-development-ticketing-service \
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
		--services ticketing-development-ticketing-service \
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
		--services ticketing-development-ticketing-service \
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
		--services ticketing-development-ticketing-service \
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
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║         ☁️  AWS Quick Reference Guide                         ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "🔥 Top 6 Most Used Commands:"
	@echo "  make aws-status             # 1️⃣ Check all services status"
	@echo "  make aws-logs               # 2️⃣ Tail API logs (real-time)"
	@echo "  make aws-restart-services   # 3️⃣ Restart ECS services (pull latest images)"
	@echo "  make aws-reset              # 4️⃣ Complete reset (restart + DB + Kafka + Kvrocks)"
	@echo "  make aws-stop               # 5️⃣ Stop all services (save money)"
	@echo "  make aws-start              # 6️⃣ Start all services"
	@echo ""
	@echo "📊 Service Status & Logs:"
	@echo "  make aws-status             # ECS services status (running/desired)"
	@echo "  make aws-logs               # API service logs"
	@echo "  make aws-logs-ticketing     # Ticketing consumer logs"
	@echo "  make aws-logs-reservation   # Reservation consumer logs"
	@echo "  make aws-api-exec           # Exec into API container shell"
	@echo ""
	@echo "🔄 Restart Individual Service (AWS CLI):"
	@echo "  aws ecs update-service --cluster ticketing-cluster --service <service-name> --force-new-deployment"
	@echo "  # Replace <service-name> with:"
	@echo "  #   - ticketing-development-ticketing-service"
	@echo "  #   - ticketing-development-booking-service"
	@echo "  #   - ticketing-development-reservation-service"
	@echo ""
	@echo "🗄️  Database Management:"
	@echo "  make aws-db-list                              # List all tables with row counts"
	@echo "  make aws-db-query TABLE=bookings LIMIT=10     # Query table data"
	@echo "  make aws-db-schema TABLE=events               # Show table schema"
	@echo "  make aws-db-migrations                        # Check migration status"
	@echo "  make aws-migrate                              # Run database migrations"
	@echo "  make aws-seed                                 # Seed initial data"
	@echo ""
	@echo "🔴 Kvrocks Inspection:"
	@echo "  make aws-kvrocks-keys                         # List all keys"
	@echo "  make aws-kvrocks-timer                        # Check event_sellout_timer:1"
	@echo "  make aws-kvrocks-get KEY=event_sellout_timer:1    # Get specific key"
	@echo "  make aws-kvrocks-status                       # Check Kvrocks service status"
	@echo ""
	@echo "🧪 Load Testing:"
	@echo "  🖥️  EC2-based (ARM64, always running, recommended):"
	@echo "    make aws-lt-exec              # Connect to LoadTest EC2 instance"
	@echo "    make aws-lt-status            # Check instance status"
	@echo "    make aws-lt-stop              # Stop instance (save cost)"
	@echo ""
	@echo "  🚀 ECS-based (x86, on-demand tasks):"
	@echo "    make aws-rlt-ecs-500          # 500 seats (20 workers, ~30s)"
	@echo "    make aws-rlt-ecs-5k           # 5,000 seats (50 workers, ~2min)"
	@echo "    make aws-rlt-ecs-25k          # 25,000 seats (75 workers, ~5min)"
	@echo "    make aws-rlt-ecs-50k          # 50,000 seats (100 workers, ~10min)"
	@echo ""
	@echo "  🐌 Local (from Mac, slow, for debugging only):"
	@echo "    make aws-go-rlt-500           # 500 seats (20 workers)"
	@echo "    make aws-go-rlt-5k            # 5,000 seats (50 workers)"
	@echo "    make aws-go-rlt-25k           # 25,000 seats (75 workers)"
	@echo "    make aws-go-rlt-50k           # 50,000 seats (100 workers)"
	@echo ""
	@echo "🚀 Reset & Seed:"
	@echo "  make aws-reset                  # Complete reset (most used)"
	@echo "  make aws-reset-db               # Reset database only"
	@echo "  make aws-reset-kafka            # Reset Kafka topics only"
	@echo "  make aws-reset-kvrocks          # Flush Kvrocks only"
	@echo "  make aws-seed-full              # Complete seed: reset-db → kafka → kvrocks → seed"
	@echo "  make aws-seed-full-500          # Seed with 500 seats (local_dev)"
	@echo "  make aws-seed-full-5k           # Seed with 5,000 seats (development)"
	@echo "  make aws-seed-full-25k          # Seed with 25,000 seats (staging)"
	@echo "  make aws-seed-full-50k          # Seed with 50,000 seats (production)"
	@echo ""
	@echo "🚀 Deployment:"
	@echo "  make dev-deploy-full            # Build + Push + Deploy (development)"
	@echo "  make staging-deploy-full        # Build + Push + Deploy (staging)"
	@echo "  make prod-deploy-full           # Build + Push + Deploy (production)"
	@echo ""
	@echo "💰 Cost Control:"
	@echo "  make aws-stop                   # Stop all services (cost ~\$$0.01/h)"
	@echo "  make aws-start                  # Start all services (wait 2 min)"
	@echo ""
	@echo "📋 Typical Workflow:"
	@echo "  Start day:  make aws-start → sleep 120 → make aws-status → make aws-seed-full"
	@echo "  Testing:    make aws-status → make aws-logs → make aws-go-rlt → make aws-kvrocks-timer"
	@echo "  Check data: make aws-kvrocks-timer  (查詢 event_sellout_timer:1)"
	@echo "  Load test:  make aws-go-rlt  (Reserved load test - buys all seats)"
	@echo "  Manual LT:  make aws-loadtest-run → make aws-loadtest-exec → cd script/go_client → ./reserved_loadtest -env development -event 1 -workers 50"
	@echo "  Quick seed: make aws-seed-full-5k  (or -500, -50k for different sizes)"
	@echo "  End day:    make aws-stop"
	@echo ""
	@echo "🔧 Manual Execution:"
	@echo "  Step 1: Reset Kafka topics (AWS command, run locally)"
	@echo "    make aws-reset-kafka"
	@echo ""
	@echo "  Step 2: Exec into API service container"
	@echo "    make aws-api-exec"
	@echo ""
	@echo "  Step 3: Run commands inside the container"
	@echo "    # 1. Reset database (drop + recreate + migrate + flush Kvrocks)"
	@echo "    uv run python -m script.reset_database"
	@echo ""
	@echo "    # 2. Seed initial data"
	@echo "    DEPLOY_ENV=development uv run python -m script.seed_data"
	@echo "    # Or: DEPLOY_ENV=local_dev (500) / DEPLOY_ENV=development (500) / DEPLOY_ENV=staging (5K) / DEPLOY_ENV=production (50K)"
	@echo ""
	@echo "  Step 4: Manual Load Test (exec into loadtest container)"
	@echo "    make aws-loadtest-run   # Start loadtest task"
	@echo "    make aws-loadtest-exec  # Exec into loadtest container"
	@echo ""
	@echo "    # Inside loadtest container, run:"
	@echo "    cd script/go_client"
	@echo "    ./reserved_loadtest -env development -event 1 -workers 50"
	@echo ""
	@echo "  Step 5: Check sellout timer in Kvrocks"
	@echo "    make aws-kvrocks-timer  # Query event_sellout_timer:1"
	@echo ""
	@echo "  Note: DEPLOY_ENV controls seat count (local_dev=500, development=5K, production=50K)"
	@echo ""
	@echo "💡 For full command list, run: make help"

# ==============================================================================
# 🔴 KVROCKS (AWS)
# ==============================================================================

.PHONY: aws-kvrocks-keys aws-kvrocks-get aws-kvrocks-timer aws-kvrocks-cli aws-kvrocks-status

aws-kvrocks-keys:  ## 🔍 List all keys in AWS Kvrocks
	@echo "🔍 Listing all keys in AWS Kvrocks..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "   ❌ No running Kvrocks instance found"; \
		exit 1; \
	fi; \
	echo "   📡 Instance: $$INSTANCE_ID"; \
	COMMAND_ID=$$(aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters 'commands=["echo \"=== Total Keys ===\"","redis-cli -h localhost -p 6666 KEYS \"*\" | wc -l","echo \"\"","echo \"=== Keys (first 20) ===\"","redis-cli -h localhost -p 6666 KEYS \"*\" | head -20"]' \
		--query 'Command.CommandId' --output text); \
	echo "   Command ID: $$COMMAND_ID"; \
	echo "   ⏳ Waiting for command to complete..."; \
	aws ssm wait command-executed --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID; \
	STATUS=$$(aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'Status' --output text); \
	if [ "$$STATUS" = "Success" ]; then \
		echo "   ✅ Command completed successfully"; \
		echo ""; \
		aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'StandardOutputContent' --output text; \
	else \
		echo "   ❌ Command failed with status: $$STATUS"; \
		aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'StandardErrorContent' --output text; \
		exit 1; \
	fi

aws-kvrocks-get:  ## 🔍 Get value of a specific key (usage: make aws-kvrocks-get KEY=event_sellout_timer:1)
	@if [ -z "$(KEY)" ]; then \
		echo "❌ Usage: make aws-kvrocks-get KEY=<key_name>"; \
		echo "Example: make aws-kvrocks-get KEY=event_sellout_timer:1"; \
		exit 1; \
	fi
	@echo "🔍 Getting value for key: $(KEY)"
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "   ❌ No running Kvrocks instance found"; \
		exit 1; \
	fi; \
	echo "   📡 Instance: $$INSTANCE_ID"; \
	COMMAND_ID=$$(aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters "commands=[\"echo '=== Key: $(KEY) ==='\",\"echo ''\",\"echo 'Type:'\",\"TYPE=\$$(redis-cli -h localhost -p 6666 TYPE $(KEY))\",\"echo \$$TYPE\",\"echo ''\",\"echo 'TTL (seconds):'\",\"redis-cli -h localhost -p 6666 TTL $(KEY)\",\"echo ''\",\"echo 'Value:'\",\"if [ \\\"\$$TYPE\\\" = \\\"string\\\" ]; then redis-cli -h localhost -p 6666 GET $(KEY); elif [ \\\"\$$TYPE\\\" = \\\"hash\\\" ]; then redis-cli -h localhost -p 6666 HGETALL $(KEY); elif [ \\\"\$$TYPE\\\" = \\\"list\\\" ]; then redis-cli -h localhost -p 6666 LRANGE $(KEY) 0 -1; elif [ \\\"\$$TYPE\\\" = \\\"set\\\" ]; then redis-cli -h localhost -p 6666 SMEMBERS $(KEY); elif [ \\\"\$$TYPE\\\" = \\\"zset\\\" ]; then redis-cli -h localhost -p 6666 ZRANGE $(KEY) 0 -1 WITHSCORES; else echo \\\"Unknown type: \$$TYPE\\\"; fi\"]" \
		--query 'Command.CommandId' --output text); \
	echo "   Command ID: $$COMMAND_ID"; \
	echo "   ⏳ Waiting for command to complete..."; \
	aws ssm wait command-executed --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID; \
	STATUS=$$(aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'Status' --output text); \
	if [ "$$STATUS" = "Success" ]; then \
		echo "   ✅ Command completed successfully"; \
		echo ""; \
		aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'StandardOutputContent' --output text; \
	else \
		echo "   ❌ Command failed with status: $$STATUS"; \
		aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'StandardErrorContent' --output text; \
		exit 1; \
	fi

aws-kvrocks-timer:  ## ⏱️  Check event_sellout_timer:1 (shortcut for event 1 sellout timer)
	@echo "⏱️  Checking event_sellout_timer:1..."
	@INSTANCE_ID=$$(aws ec2 describe-instances \
		--filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ] || [ "$$INSTANCE_ID" = "None" ]; then \
		echo "   ❌ No running Kvrocks instance found"; \
		exit 1; \
	fi; \
	echo "   📡 Instance: $$INSTANCE_ID"; \
	COMMAND_ID=$$(aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters 'commands=["echo \"=== Event 1 Sellout Timer ===\"","echo \"\"","echo \"Type:\"","redis-cli -h localhost -p 6666 TYPE event_sellout_timer:1","echo \"\"","echo \"TTL (seconds):\"","redis-cli -h localhost -p 6666 TTL event_sellout_timer:1","echo \"\"","echo \"Hash Fields:\"","redis-cli -h localhost -p 6666 HGETALL event_sellout_timer:1","echo \"\"","echo \"Formatted:\"","redis-cli -h localhost -p 6666 HGETALL event_sellout_timer:1 | awk '\''{if(NR%2==1) printf \"%s: \", $$0; else print $$0}'\''"]' \
		--query 'Command.CommandId' --output text); \
	echo "   Command ID: $$COMMAND_ID"; \
	echo "   ⏳ Waiting for command to complete..."; \
	aws ssm wait command-executed --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID; \
	STATUS=$$(aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'Status' --output text); \
	if [ "$$STATUS" = "Success" ]; then \
		echo "   ✅ Command completed successfully"; \
		echo ""; \
		aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'StandardOutputContent' --output text; \
	else \
		echo "   ❌ Command failed with status: $$STATUS"; \
		aws ssm get-command-invocation --command-id $$COMMAND_ID --instance-id $$INSTANCE_ID --query 'StandardErrorContent' --output text; \
		exit 1; \
	fi

aws-kvrocks-cli:  ## 🔧 Open interactive redis-cli to AWS Kvrocks (requires installation on EC2)
	@echo "🔧 Opening redis-cli to AWS Kvrocks..."
	@INSTANCE_ID=$$(aws autoscaling describe-auto-scaling-groups \
		--auto-scaling-group-names $$(aws autoscaling describe-auto-scaling-groups --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Kvrocks`)].AutoScalingGroupName' --output text) \
		--query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ]; then \
		echo "❌ No Kvrocks instance found"; \
		exit 1; \
	fi; \
	echo "📡 Instance: $$INSTANCE_ID"; \
	echo "⚠️  Note: This requires redis-tools to be installed on the EC2 instance"; \
	echo ""; \
	aws ssm start-session --target $$INSTANCE_ID

aws-kvrocks-status:  ## 📊 Check AWS Kvrocks service status
	@echo "📊 Checking AWS Kvrocks status..."
	@INSTANCE_ID=$$(aws autoscaling describe-auto-scaling-groups \
		--auto-scaling-group-names $$(aws autoscaling describe-auto-scaling-groups --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Kvrocks`)].AutoScalingGroupName' --output text) \
		--query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId' --output text); \
	if [ -z "$$INSTANCE_ID" ]; then \
		echo "❌ No Kvrocks instance found"; \
		exit 1; \
	fi; \
	echo "📡 Instance: $$INSTANCE_ID"; \
	CMD_ID=$$(aws ssm send-command \
		--instance-ids $$INSTANCE_ID \
		--document-name "AWS-RunShellScript" \
		--parameters 'commands=["systemctl status kvrocks --no-pager | head -20"]' \
		--query 'Command.CommandId' --output text); \
	echo "⏳ Waiting for command to complete..."; \
	sleep 3; \
	aws ssm get-command-invocation \
		--command-id $$CMD_ID \
		--instance-id $$INSTANCE_ID \
		--query 'StandardOutputContent' --output text

.DEFAULT_GOAL := aws-help
