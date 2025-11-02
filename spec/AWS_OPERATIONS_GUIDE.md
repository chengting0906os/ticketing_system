# AWS Operations & Deployment Guide

Complete guide for deploying and operating the Ticketing System on AWS infrastructure.

**Cost-Optimized Architecture** - EC2 Kafka saves 95% vs MSK (~$24/month vs $466/month)

---

## 📋 Architecture Overview

| Stack | Components | Deploy Time |
|-------|-----------|-------------|
| TicketingAuroraStack | VPC + Aurora + ALB + ECS Cluster | ~15 min |
| TicketingEC2KafkaStack | EC2 Kafka (3 brokers, KRaft mode) | ~5 min |
| TicketingKvrocksStack | Redis cache (ECS + EFS) | ~5 min |
| APIServiceStack | Unified API endpoint | ~5 min |
| TicketingConsumerStack | Booking event consumer | ~10 min |
| ReservationConsumerStack | Seat reservation consumer | ~10 min |

**Total deployment time:** ~50 minutes

---

## 🚀 Initial Deployment (3 Steps)

### 1. Prerequisites

```bash
# Install tools
brew install awscli node python@3.13
npm install -g aws-cdk

# Configure AWS
aws configure
# Region: us-west-2

# Bootstrap CDK (once per account/region)
cd deployment/cdk
cdk bootstrap aws://YOUR_ACCOUNT_ID/us-west-2
```

### 2. Push Docker Images to ECR

**⚠️ CRITICAL: Must complete BEFORE deploying ECS services**

```bash
# Production environment
./deployment/script/ecr-push.sh production all

# Development environment
./deployment/script/ecr-push.sh development all

# Wait ~10-15 minutes
# Expected output:
# ✅ Pushed: ticketing-service:latest
# ✅ Pushed: ticketing-consumer:latest
# ✅ Pushed: seat-reservation-consumer:latest
```

### 3. Deploy All Stacks

```bash
# Production
export DEPLOY_ENV=production
make cdk-deploy-all

# Development (lower cost for testing)
export DEPLOY_ENV=development
make dev-deploy-all

# Wait ~50 minutes
```

**Verify deployment:**

```bash
# Check all services
make aws-status

# Get ALB endpoint
aws cloudformation describe-stacks \
  --stack-name TicketingAuroraStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ALBEndpoint`].OutputValue' \
  --output text

# Test API health
curl http://<ALB-ENDPOINT>/health
# Expected: {"status": "healthy"}
```

---

## 💡 Quick Reference: Local vs AWS Commands

| Local Docker | AWS Cloud | Description |
|-------------|-----------|-------------|
| `make dra` | `make aws-reset` | Complete reset: restart all services, migrate DB, reset Kafka, seed data |
| `make dm` | `make aws-migrate` | Run database migrations |
| `make drk` | `make aws-reset-kafka` | Reset Kafka topics (delete + recreate) |
| `make ds` | `make aws-seed` | Seed initial data |
| `make dc` | `make aws-status` | Check service status |
| `docker logs -f api` | `make aws-logs` | View API service logs |

---

## 🚀 Complete Reset (Cloud version of `make dra`)

```bash
make aws-reset
```

**What it does:**
1. ✅ Restarts all ECS services (API + 2 consumer services)
2. ✅ Runs database migrations on Aurora
3. ✅ Resets Kafka topics (delete + recreate with proper config)
4. ✅ Seeds initial data
5. ✅ Waits for services to be healthy

**Use this when:**
- Starting fresh testing on AWS
- After deploying new infrastructure changes
- Debugging production-like environment issues

---

## 🗄️ Database Operations

### Run Migrations
```bash
make aws-migrate
```

This starts a **one-time ECS task** that runs `alembic upgrade head` against Aurora.

### Seed Data
```bash
make aws-seed
```

Runs the seed script as a one-time ECS task.

### Direct Database Access
```bash
# Get Aurora endpoint
aws rds describe-db-clusters \
  --db-cluster-identifier ticketing-aurora-cluster \
  --query 'DBClusters[0].Endpoint' --output text

# Get credentials from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id ticketing/aurora/credentials \
  --query 'SecretString' --output text | jq -r '.password'

# Connect via bastion (if you have one) or use aurora_inspect.py
python deployment/script/aurora_inspect.py
```

---

## 🌊 Kafka Operations

### Reset Kafka Topics
```bash
make aws-reset-kafka
```

**What it does:**
1. Finds the EC2 Kafka instance ID
2. Connects via AWS SSM (no SSH keys needed!)
3. Deletes existing topics: `ticketing-events`, `seat-reservation-events`
4. Recreates topics with:
   - **6 partitions** (for parallel consumer processing)
   - **Replication factor 3** (across 3 Kafka brokers)

### Manual Kafka Commands via SSM

```bash
# Get Kafka EC2 instance ID
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

# List topics
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/kafka && docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --list"]'

# Check consumer lag
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/kafka && docker-compose exec -T kafka-1 kafka-consumer-groups --bootstrap-server localhost:9092 --describe --all-groups"]'
```

---

## 📊 Service Management

### Check All Services Status
```bash
make aws-status
```

Shows:
- Service name
- Status (ACTIVE/INACTIVE)
- Running task count
- Desired task count

### Restart a Service
```bash
# Restart API service
aws ecs update-service --cluster ticketing-cluster \
  --service ticketing-development-api-service --force-new-deployment

# Restart ticketing consumer
aws ecs update-service --cluster ticketing-cluster \
  --service ticketing-development-ticketing-consumer-service --force-new-deployment

# Restart reservation consumer
aws ecs update-service --cluster ticketing-cluster \
  --service ticketing-development-reservation-consumer-service --force-new-deployment
```

### Scale Services
```bash
# Scale ticketing consumer to 3 tasks
aws ecs update-service --cluster ticketing-cluster \
  --service ticketing-development-ticketing-consumer-service --desired-count 3

# Scale reservation consumer to 3 tasks
aws ecs update-service --cluster ticketing-cluster \
  --service ticketing-development-reservation-consumer-service --desired-count 3
```

---

## 🔍 Logging and Debugging

### Tail API Logs
```bash
make aws-logs
```

### Tail Consumer Logs
```bash
# Ticketing consumer
aws logs tail /ecs/ticketing-development-ticketing-consumer --follow

# Reservation consumer
aws logs tail /ecs/ticketing-development-reservation-consumer --follow
```

### View Recent Errors
```bash
aws logs filter-pattern /ecs/ticketing-development-api \
  --filter-pattern "ERROR" \
  --start-time $(date -u -d '1 hour ago' +%s)000
```

### Check ECS Task Details
```bash
# List running tasks
aws ecs list-tasks --cluster ticketing-cluster

# Get task details
aws ecs describe-tasks --cluster ticketing-cluster \
  --tasks <task-arn>
```

---

## 🏗️ Infrastructure Operations

### Deploy All Stacks (Development)
```bash
make dev-deploy-all
```

### Check Aurora Configuration
```bash
make cdk-check-env
```

### View Stack Outputs
```bash
aws cloudformation describe-stacks \
  --stack-name TicketingAuroraStack \
  --query 'Stacks[0].Outputs' --output table
```

---

## 💡 Common Workflows

### Fresh Start on AWS
```bash
# 1. Deploy infrastructure (if not already deployed)
make dev-deploy-all

# 2. Wait for deployment to complete (~10 minutes)

# 3. Complete reset (migrate + seed + reset Kafka)
make aws-reset

# 4. Check everything is running
make aws-status
```

### Update Code and Redeploy
```bash
# 1. Build and push new Docker images
./deployment/script/ecr-push.sh

# 2. Restart services to use new images
make aws-reset

# 3. Monitor logs
make aws-logs
```

### Debug Consumer Issues
```bash
# 1. Check service status
make aws-status

# 2. Check Kafka topics
make aws-reset-kafka

# 3. Tail consumer logs
aws logs tail /ecs/ticketing-development-ticketing-consumer --follow

# 4. Check consumer lag
# (use SSM command shown in Kafka Operations section)
```

---

## 🆘 Troubleshooting

### Services Not Starting
```bash
# Check ECS service events
aws ecs describe-services --cluster ticketing-cluster \
  --services ticketing-development-api-service \
  --query 'services[0].events[0:5]'

# Check task stopped reasons
aws ecs describe-tasks --cluster ticketing-cluster \
  --tasks $(aws ecs list-tasks --cluster ticketing-cluster --query 'taskArns[0]' --output text) \
  --query 'tasks[0].stoppedReason'
```

### Kafka Connection Issues
```bash
# 1. Check Kafka EC2 instance is running
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*KafkaInstance*" \
  --query 'Reservations[0].Instances[0].State.Name'

# 2. Check Kafka containers are running
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'

# 3. Check Kafka logs
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/kafka && docker-compose logs kafka-1 --tail 100"]'
```

### Database Connection Issues
```bash
# Check Aurora cluster status
aws rds describe-db-clusters \
  --db-cluster-identifier ticketing-aurora-cluster \
  --query 'DBClusters[0].Status'

# Check security group allows connections from ECS tasks
aws ec2 describe-security-groups \
  --filters "Name=tag:aws:cloudformation:logical-id,Values=AuroraSecurityGroup"
```

---

## 🛑 Cost Optimization - Stop/Start Services

### Stop All Services (Keep Aurora Only)

```bash
make aws-stop
```

**What it does:**
- Scales all ECS services to 0 (API + consumers + Kvrocks)
- Stops EC2 Kafka instance
- Keeps Aurora running at minimum ACU (0.5)

**Cost:** ~$0.01/hour (Aurora only)

### Restart All Services

```bash
make aws-start
```

**What it does:**
- Restarts EC2 Kafka instance
- Scales all ECS services back to desired count
- Waits for services to be healthy

---

## 🔄 Update Application Code

```bash
# 1. Push new Docker images
./deployment/script/ecr-push.sh production all

# 2. Restart services with new images
make aws-reset

# 3. Monitor deployment
make aws-logs
```

---

## 💰 Cost Breakdown

### Development Environment

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| Aurora Serverless v2 | 0.5-16 ACU (avg 2) | $29 |
| EC2 Kafka | t4g.medium + 50GB EBS | $24 |
| ECS API | 1 task × 2 vCPU | $30 |
| ECS Consumers | 2 tasks × 1 vCPU | $30 |
| Kvrocks | 1 task × 1 vCPU | $15 |
| ALB | - | $22 |
| NAT Gateway | - | $32 |
| **Total** | | **~$182/month** |

### Production Environment

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| Aurora Serverless v2 | 0.5-64 ACU (avg 8) | $680 |
| EC2 Kafka | t4g.medium + 50GB EBS | $24 |
| ECS API | 1-4 tasks × 8 vCPU | $120-480 |
| ECS Consumers | 100-200 tasks × 1 vCPU | $1440-2880 |
| Kvrocks | 1 task × 1 vCPU | $15 |
| ALB | - | $22 |
| NAT Gateway | - | $32 |
| CloudWatch Logs | 50 GB | $25 |
| **Total** | | **~$2,338-4,138/month** |

**Savings vs MSK:** $442/month (95% reduction on Kafka costs)

---

## 🗑️ Cleanup Resources

```bash
# Destroy all stacks
make dev-destroy-all
# or
make cdk-destroy-all

# Delete ECR repositories (optional)
aws ecr delete-repository --repository-name ticketing-service --force
aws ecr delete-repository --repository-name ticketing-consumer --force
aws ecr delete-repository --repository-name seat-reservation-consumer --force
```

---

## 🗄️ Database Operations & Inspection

### Aurora Database Commands

Since Aurora is inside a private VPC, we use ECS tasks to inspect the database:

```bash
# Check migration status
make aws-db-migrations

# List all tables with row counts
make aws-db-list

# Show table schema
make aws-db-schema TABLE=events
make aws-db-schema TABLE=bookings

# Query table data
make aws-db-query TABLE=events LIMIT=10
```

### How Database Inspection Works

1. Starts an ECS Fargate task using your API container
2. Runs [deployment/script/aurora_inspect.py](../deployment/script/aurora_inspect.py) inside the container
3. Captures CloudWatch logs from task execution
4. Displays results in your terminal

### Aurora Performance Monitoring

```bash
# Check current ACU usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name ServerlessDatabaseCapacity \
  --dimensions Name=DBClusterIdentifier,Value=ticketing-aurora-cluster \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average

# View Performance Insights (AWS Console)
# Go to RDS → ticketing-aurora-cluster → Performance Insights
```

**Key Metrics to Monitor:**
- `DatabaseConnections` - Active connections
- `CPUUtilization` - CPU usage
- `ServerlessDatabaseCapacity` - Current ACU usage
- `ReadLatency` / `WriteLatency` - Query performance

---

## 🆘 Common Issues

### Issue: Circuit Breaker Triggered

**Cause:** Docker images not pushed to ECR before deployment

**Fix:**
```bash
# Verify images exist
aws ecr list-images --repository-name ticketing-service
aws ecr list-images --repository-name ticketing-consumer
aws ecr list-images --repository-name seat-reservation-consumer

# Should see 'latest' tag. If missing:
./deployment/script/ecr-push.sh production all
```

### Issue: API Service Failed to Start

**Cause:** Module path error or database connection issue

**Fix:**
```bash
# Check logs for errors
make aws-logs

# Common issues:
# 1. Wrong module path (should be: src.main:app)
# 2. Aurora not ready (wait for cluster status: available)
# 3. Security group blocking connections
```

### Issue: Stack in UPDATE_IN_PROGRESS

**Fix:**
```bash
# Wait for update to complete
aws cloudformation wait stack-update-complete \
  --stack-name TicketingAuroraStack

# Or deploy specific stacks only
export DEPLOY_ENV=production
cdk deploy APIServiceStack TicketingConsumerStack ReservationConsumerStack
```

### Issue: Task Failures

**Check stopped tasks:**
```bash
# List stopped tasks
aws ecs list-tasks --cluster ticketing-cluster --desired-status STOPPED

# Get failure reason
aws ecs describe-tasks --cluster ticketing-cluster --tasks <TASK_ARN> \
  --query 'tasks[0].stoppedReason'
```

**Common causes:**
- Image pull failed → Check ECR permissions
- Out of memory → Increase task memory in config.yml
- Environment variable errors → Check Secrets Manager

### Issue: ALB Health Check Failed

```bash
# Check target health
TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
  --query 'TargetGroups[?contains(TargetGroupName, `APITargets`)].TargetGroupArn' \
  --output text)

aws elbv2 describe-target-health --target-group-arn $TARGET_GROUP_ARN

# Debug container health endpoint
aws ecs execute-command --cluster ticketing-cluster \
  --task <TASK_ID> --container Container \
  --command "/bin/sh" --interactive
```

### Issue: Consumer Can't Connect to Kafka

```bash
# Check EC2 Kafka instance status
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*KafkaInstance*" \
  --query 'Reservations[0].Instances[0].State.Name'

# Connect to Kafka instance and check Docker containers
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*KafkaInstance*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

aws ssm send-command --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'
```

---

## 📚 Related Documentation

- [Makefile](../Makefile) - All available commands (`make help`)
- [config.yml](config.yml) - Environment configuration
- [CDK Stacks](cdk/stacks/) - Infrastructure as code
- [aurora_inspect.py](../deployment/script/aurora_inspect.py) - Database inspection script

### AWS Console Quick Links

- **ECS Cluster**: https://console.aws.amazon.com/ecs/home?region=us-west-2#/clusters/ticketing-cluster
- **Aurora DB**: https://console.aws.amazon.com/rds/home?region=us-west-2
- **CloudWatch**: https://console.aws.amazon.com/cloudwatch/home?region=us-west-2
- **Secrets Manager**: https://console.aws.amazon.com/secretsmanager/home?region=us-west-2

---

**Version:** 4.0 (EC2 Kafka + Complete Operations & Deployment)
**Last Updated:** 2025-11-03
**Region:** us-west-2
**Maintainer:** CTC
