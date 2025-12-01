# ==============================================================================
# ☁️ AWS OPERATIONS MAKEFILE (Simplified)
# ==============================================================================
# Usage: make -f deployment/Makefile <target>
# ==============================================================================

AWS_REGION ?= us-west-2
DEPLOY_ENV ?= development

# ==============================================================================
# 🚀 CORE OPERATIONS
# ==============================================================================

.PHONY: aws-start aws-stop aws-status aws-logs aws-restart

aws-start:  ## ▶️ Start all AWS services
	@echo "▶️ Starting all services..."
	@# Start Kvrocks ASG
	@ASG_NAME=$$(aws autoscaling describe-auto-scaling-groups \
		--query 'AutoScalingGroups[?contains(Tags[?Key==`aws:cloudformation:stack-name`].Value, `TicketingKvrocksStack`)].AutoScalingGroupName' \
		--output text); \
	if [ -n "$$ASG_NAME" ] && [ "$$ASG_NAME" != "None" ]; then \
		aws autoscaling set-desired-capacity --auto-scaling-group-name $$ASG_NAME --desired-capacity 1; \
		echo "✅ Kvrocks ASG starting"; \
	fi
	@# Start Kafka EC2s
	@aws ec2 start-instances --instance-ids \
		$$(aws ec2 describe-instances --filters "Name=tag:Name,Values=kafka-broker-*" --query 'Reservations[*].Instances[*].InstanceId' --output text) 2>/dev/null || true
	@echo "✅ Kafka EC2s starting"
	@echo "⏳ Wait 60s for infrastructure..."
	@sleep 60
	@# Scale ECS services
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-ticketing-service --desired-count 1 >/dev/null 2>&1 || true
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-booking-service --desired-count 2 >/dev/null 2>&1 || true
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-reservation-service --desired-count 2 >/dev/null 2>&1 || true
	@echo "✅ All services started"

aws-stop:  ## 🛑 Stop all AWS services (save cost)
	@echo "🛑 Stopping all services..."
	@# Scale ECS to 0
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-ticketing-service --desired-count 0 >/dev/null 2>&1 || true
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-booking-service --desired-count 0 >/dev/null 2>&1 || true
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-reservation-service --desired-count 0 >/dev/null 2>&1 || true
	@# Stop Kafka EC2s
	@aws ec2 stop-instances --instance-ids \
		$$(aws ec2 describe-instances --filters "Name=tag:Name,Values=kafka-broker-*" "Name=instance-state-name,Values=running" --query 'Reservations[*].Instances[*].InstanceId' --output text) 2>/dev/null || true
	@# Scale Kvrocks ASG to 0
	@ASG_NAME=$$(aws autoscaling describe-auto-scaling-groups \
		--query 'AutoScalingGroups[?contains(Tags[?Key==`aws:cloudformation:stack-name`].Value, `TicketingKvrocksStack`)].AutoScalingGroupName' \
		--output text); \
	if [ -n "$$ASG_NAME" ] && [ "$$ASG_NAME" != "None" ]; then \
		aws autoscaling set-desired-capacity --auto-scaling-group-name $$ASG_NAME --desired-capacity 0; \
	fi
	@echo "✅ All services stopped"

aws-status:  ## 📊 Check service status
	@echo "📊 ECS Services:"
	@aws ecs describe-services --cluster ticketing-cluster \
		--services ticketing-development-ticketing-service ticketing-development-booking-service ticketing-development-reservation-service \
		--query 'services[].[serviceName,runningCount,desiredCount]' --output table 2>/dev/null || echo "No services found"
	@echo ""
	@echo "📊 Kafka EC2:"
	@aws ec2 describe-instances --filters "Name=tag:Name,Values=kafka-broker-*" \
		--query 'Reservations[*].Instances[*].[Tags[?Key==`Name`].Value|[0],State.Name]' --output table
	@echo ""
	@echo "📊 Kvrocks ASG:"
	@aws autoscaling describe-auto-scaling-groups \
		--query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Kvrocks`)].[AutoScalingGroupName,DesiredCapacity]' --output table

aws-logs:  ## 🔍 Tail API logs
	@aws logs tail /ecs/ticketing-development-ticketing-service --follow --format short 2>/dev/null || \
		aws logs tail $$(aws ecs describe-task-definition --task-definition $$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-ticketing-service --query 'services[0].taskDefinition' --output text) --query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text) --follow --format short

aws-restart:  ## 🔄 Restart ECS services (pull latest images)
	@echo "🔄 Restarting ECS services..."
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-ticketing-service --force-new-deployment >/dev/null
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-booking-service --force-new-deployment >/dev/null
	@aws ecs update-service --cluster ticketing-cluster --service ticketing-development-reservation-service --force-new-deployment >/dev/null
	@echo "✅ Restart triggered, waiting for stable..."
	@aws ecs wait services-stable --cluster ticketing-cluster \
		--services ticketing-development-ticketing-service ticketing-development-booking-service ticketing-development-reservation-service
	@echo "✅ All services stable"

# ==============================================================================
# 🗄️ DATABASE & RESET
# ==============================================================================

.PHONY: aws-migrate aws-reset-kafka aws-reset-kvrocks aws-api-exec

aws-migrate:  ## 🗄️ Run database migrations
	@echo "🗄️ Running migrations..."
	@TASK_DEF=$$(aws ecs describe-services --cluster ticketing-cluster --services ticketing-development-ticketing-service --query 'services[0].taskDefinition' --output text); \
	SUBNET=$$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=TicketingAuroraStack/TicketingVpc/PrivateSubnet*" --query 'Subnets[0].SubnetId' --output text); \
	SG=$$(aws ec2 describe-security-groups --filters "Name=group-name,Values=*AuroraSecurityGroup*" --query 'SecurityGroups[0].GroupId' --output text); \
	TASK_ARN=$$(aws ecs run-task --cluster ticketing-cluster --task-definition $$TASK_DEF --launch-type FARGATE \
		--network-configuration "awsvpcConfiguration={subnets=[$$SUBNET],securityGroups=[$$SG]}" \
		--overrides '{"containerOverrides":[{"name":"Container","command":["uv","run","alembic","-c","alembic.ini","upgrade","head"]}]}' \
		--query 'tasks[0].taskArn' --output text); \
	echo "⏳ Waiting..."; \
	aws ecs wait tasks-stopped --cluster ticketing-cluster --tasks $$TASK_ARN; \
	echo "✅ Migration done"

aws-reset-kafka:  ## 🌊 Reset Kafka topics
	@echo "🌊 Resetting Kafka topics..."
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:Name,Values=kafka-broker-1" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	aws ssm send-command --instance-ids $$INSTANCE_ID --document-name "AWS-RunShellScript" \
		--parameters 'commands=["cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic ticketing-events || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic seat-reservation-events || true","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic ticketing-events --partitions 100 --replication-factor 3","cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic seat-reservation-events --partitions 100 --replication-factor 3"]' >/dev/null
	@echo "✅ Kafka topics reset"

aws-reset-kvrocks:  ## 🗑️ Flush Kvrocks
	@echo "🗑️ Flushing Kvrocks..."
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	aws ssm send-command --instance-ids $$INSTANCE_ID --document-name "AWS-RunShellScript" \
		--parameters 'commands=["redis-cli -h localhost -p 6666 FLUSHDB"]' >/dev/null
	@echo "✅ Kvrocks flushed"

aws-api-exec:  ## 🔧 Exec into API container
	@TASK_ARN=$$(aws ecs list-tasks --cluster ticketing-cluster --service-name ticketing-development-ticketing-service --desired-status RUNNING --query 'taskArns[0]' --output text); \
	aws ecs execute-command --cluster ticketing-cluster --task $$TASK_ARN --container Container --interactive --command "/bin/bash"

# ==============================================================================
# 🖥️ EC2 LOADTEST
# ==============================================================================

.PHONY: aws-lt-exec aws-lt-start aws-lt-stop

aws-lt-exec:  ## 🔧 Connect to LoadTest EC2
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:Name,Values=LoadTest-Instance" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	echo "📡 Connecting to $$INSTANCE_ID..."; \
	echo "🎯 Run: cd ~/app/script/go_client && ./reserved_loadtest -env development -event 1 -workers 50"; \
	aws ssm start-session --target $$INSTANCE_ID

aws-lt-start:  ## 🚀 Start LoadTest EC2
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:Name,Values=LoadTest-Instance" --query 'Reservations[0].Instances[0].InstanceId' --output text); \
	aws ec2 start-instances --instance-ids $$INSTANCE_ID >/dev/null; \
	echo "✅ LoadTest instance starting"

aws-lt-stop:  ## 🛑 Stop LoadTest EC2
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:Name,Values=LoadTest-Instance" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	aws ec2 stop-instances --instance-ids $$INSTANCE_ID >/dev/null 2>&1 || true; \
	echo "✅ LoadTest instance stopped"

# ==============================================================================
# 🚀 DEPLOYMENT
# ==============================================================================

.PHONY: ecr-push cdk-deploy dev-deploy-full

ecr-push:  ## 📦 Push Docker images to ECR
	@./deployment/script/ecr-push.sh $(DEPLOY_ENV) all

cdk-deploy:  ## 🚀 Deploy CDK stacks
	@DEPLOY_ENV=$(DEPLOY_ENV) uv run cdk deploy --all --require-approval never

dev-deploy-full:  ## 🎯 Build + Push + Deploy (complete)
	@echo "📦 Step 1/2: Pushing to ECR..."
	@./deployment/script/ecr-push.sh development all
	@echo "🚀 Step 2/2: Deploying CDK..."
	@DEPLOY_ENV=development uv run cdk deploy --all --require-approval never
	@echo "✅ Deployment complete"

# ==============================================================================
# 🔴 KVROCKS
# ==============================================================================

.PHONY: aws-kvrocks-timer aws-kvrocks-keys

aws-kvrocks-timer:  ## ⏱️ Check event_sellout_timer:1
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	CMD_ID=$$(aws ssm send-command --instance-ids $$INSTANCE_ID --document-name "AWS-RunShellScript" \
		--parameters 'commands=["redis-cli -h localhost -p 6666 HGETALL event_sellout_timer:1"]' --query 'Command.CommandId' --output text); \
	sleep 3; \
	aws ssm get-command-invocation --command-id $$CMD_ID --instance-id $$INSTANCE_ID --query 'StandardOutputContent' --output text

aws-kvrocks-keys:  ## 🔍 List Kvrocks keys
	@INSTANCE_ID=$$(aws ec2 describe-instances --filters "Name=tag:aws:autoscaling:groupName,Values=*KvrocksASG*" "Name=instance-state-name,Values=running" \
		--query 'Reservations[0].Instances[0].InstanceId' --output text); \
	CMD_ID=$$(aws ssm send-command --instance-ids $$INSTANCE_ID --document-name "AWS-RunShellScript" \
		--parameters 'commands=["redis-cli -h localhost -p 6666 KEYS \"*\" | head -30"]' --query 'Command.CommandId' --output text); \
	sleep 3; \
	aws ssm get-command-invocation --command-id $$CMD_ID --instance-id $$INSTANCE_ID --query 'StandardOutputContent' --output text

.DEFAULT_GOAL := help

help:  ## 📋 Show commands
	@echo "╔══════════════════════════════════════════════╗"
	@echo "║      ☁️  AWS Operations (Simplified)         ║"
	@echo "╚══════════════════════════════════════════════╝"
	@echo ""
	@echo "🚀 Core:"
	@echo "  aws-start          Start all services"
	@echo "  aws-stop           Stop all (save cost)"
	@echo "  aws-status         Check status"
	@echo "  aws-logs           Tail API logs"
	@echo "  aws-restart        Restart ECS services"
	@echo ""
	@echo "🗄️ Database:"
	@echo "  aws-migrate        Run migrations"
	@echo "  aws-reset-kafka    Reset Kafka topics"
	@echo "  aws-reset-kvrocks  Flush Kvrocks"
	@echo "  aws-api-exec       Exec into API container"
	@echo ""
	@echo "🖥️ LoadTest EC2:"
	@echo "  aws-lt-exec        Connect to instance"
	@echo "  aws-lt-start       Start instance"
	@echo "  aws-lt-stop        Stop instance"
	@echo ""
	@echo "🚀 Deploy:"
	@echo "  ecr-push           Push Docker images"
	@echo "  cdk-deploy         Deploy CDK"
	@echo "  dev-deploy-full    Build + Push + Deploy"
	@echo ""
	@echo "🔴 Kvrocks:"
	@echo "  aws-kvrocks-timer  Check sellout timer"
	@echo "  aws-kvrocks-keys   List keys"
