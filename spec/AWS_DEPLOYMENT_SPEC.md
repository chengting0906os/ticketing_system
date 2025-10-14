# AWS Production Deployment Guide

10000 TPS High-Availability Architecture

## Architecture

```text
                 Internet
                    │
                    ▼
              ┌─────────┐
              │   ALB   │
              └────┬────┘
                   │
     ┌─────────────┴─────────────┐
     │                           │
     ▼                           ▼
┌────────────┐          ┌────────────────┐
│ Ticketing  │◄────────►│ Seat           │
│ Service    │  Kafka   │ Reservation    │
│ (ECS)      │          │ Service (ECS)  │
│ 4-16 tasks │          │ 4-16 tasks     │
└─────┬──────┘          └──────┬─────────┘
      │                        │
      └──┬──────────┬──────────┘
         │          │          │
         ▼          ▼          ▼
    ┌───────┐  ┌──────┐  ┌────────┐
    │Aurora │  │ MSK  │  │Kvrocks │
    │2-64ACU│  │Kafka │  │1M+2R+3S│
    │1W+1R  │  │3-node│  │        │
    └───────┘  └──────┘  └────────┘
```

## Components

| Component | Spec | Monthly Cost | Purpose |
|-----------|------|--------------|---------|
| **Aurora Serverless v2** | 2-64 ACU, 1W+1R | $500-$15,000 | PostgreSQL |
| **Amazon MSK** | 3×kafka.m5.large | $300-$500 | Kafka cluster |
| **ECS Fargate** | 2 services×(4-16 tasks) | $400-$1,600 | Microservices |
| **Kvrocks on ECS** | 1M+2R+3S | $100-$200 | Redis cache |
| **ALB** | - | $16-$25 | Load balancing |
| **EFS** | Persistent storage | $30-$100 | Kvrocks data |
| **Secrets Manager** | - | $5-$10 | Credentials |
| **CloudWatch** | Logs + Metrics | $50-$100 | Monitoring |
| **Total** | - | **$1,410-$17,560** | - |

💡 **Typical cost** at 2000-5000 TPS: **$1,500-$3,000/month**

## Prerequisites

### 1. AWS CLI

```bash
# Install
brew install awscli  # macOS

# Configure
aws configure
# Access Key ID: your-key
# Secret Access Key: your-secret
# Region: us-east-1
# Output format: json
```

### 2. Push Docker Images to ECR

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Build & push ticketing-service
docker build -t ticketing-service:latest -f Dockerfile.ticketing .
docker tag ticketing-service:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/ticketing-service:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/ticketing-service:latest

# Build & push seat-reservation-service
docker build -t seat-reservation-service:latest -f Dockerfile.reservation .
docker tag seat-reservation-service:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/seat-reservation-service:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/seat-reservation-service:latest
```

### 3. CDK Bootstrap

```bash
uv run cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
```

## Deployment Steps

### Stage 1: Infrastructure (30-45 min)

```bash
# 1. Aurora (10-15 min)
uv run cdk deploy TicketingAuroraStack

# 2. MSK Kafka (20-30 min)
uv run cdk deploy TicketingMSKStack

# 3. Kvrocks (5-10 min)
uv run cdk deploy TicketingKvrocksStack
```

### Stage 2: Application (10-15 min)

```bash
# 4. ECS Services
uv run cdk deploy TicketingECSStack

# 5. Load Test Runner (Optional - for performance testing)
uv run cdk deploy TicketingLoadTestStack
```

### One-Command Deploy (Not recommended for first time)

```bash
# Deploy all (30-45 min total)
uv run cdk deploy --all --require-approval never
```

## ALB Path-Based Routing

ALB automatically routes requests to the correct service based on URL path:

```text
Internet → ALB (port 80/443)
              │
              ├─ /api/user/*        → ticketing-service:8000
              ├─ /api/event/*       → ticketing-service:8000
              ├─ /api/booking/*     → ticketing-service:8000
              └─ /api/reservation/* → seat-reservation-service:8000
```

**Example Requests**:

```bash
# All requests go to same ALB endpoint
curl https://alb-xxx.elb.amazonaws.com/api/user/login
# → Routes to ticketing-service

curl https://alb-xxx.elb.amazonaws.com/api/reservation/123
# → Routes to seat-reservation-service
```

## Environment Variables

Services configured via ECS Task Definition + Secrets Manager:

```bash
# Aurora
DATABASE_WRITER_URL=postgresql://admin:<password>@<writer-endpoint>:5432/ticketing_db
DATABASE_READER_URL=postgresql://admin:<password>@<reader-endpoint>:5432/ticketing_db

# MSK
KAFKA_BOOTSTRAP_SERVERS=<b1>:9098,<b2>:9098,<b3>:9098

# Kvrocks (via Sentinel)
REDIS_SENTINELS=sentinel-1:26666,sentinel-2:26666,sentinel-3:26666
REDIS_MASTER_NAME=mymaster

# Service Discovery
SERVICE_DISCOVERY_NAMESPACE=ticketing.local
```

## Verification

```bash
# Health check
curl http://<alb-dns>/api/user/health

# Expected: {"status": "ok"}
```

## Monitoring

### CloudWatch Dashboards

Auto-created dashboards:

- **ECS**: CPU/Memory, Container count
- **Aurora**: Connections, IOPS, CPU
- **MSK**: Throughput, Lag
- **ALB**: Requests, Latency, Target health

### Recommended Alarms

```bash
# ECS CPU > 80%
aws cloudwatch put-metric-alarm \
  --alarm-name ECS-CPU-High \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold

# Aurora Connections > 80%
aws cloudwatch put-metric-alarm \
  --alarm-name Aurora-Connections-High \
  --metric-name DatabaseConnections \
  --namespace AWS/RDS \
  --threshold 800
```

## Troubleshooting

### ECS tasks won't start

```bash
aws ecs describe-tasks --cluster ticketing-cluster --tasks <task-id>
# Common: ECR image missing, IAM permission, env vars
```

### Aurora connection failed

```bash
aws ec2 describe-security-groups --group-ids <aurora-sg-id>
# Ensure ECS security group can access Aurora
```

### Kvrocks connection failed

```bash
aws ecs execute-command \
  --cluster ticketing-cluster \
  --task <sentinel-task-id> \
  --container Sentinel \
  --command "redis-cli -p 26666 SENTINEL masters"
```

## Load Testing

### Deploy Prerequisites

Build and push the loadtest Docker image:

```bash
# Build loadtest image (from go_client directory)
cd script/go_client
docker build -t loadtest-runner:latest .

# Tag and push to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
docker tag loadtest-runner:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/loadtest-runner:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/loadtest-runner:latest
```

### Run Load Test

```bash
# Get task definition ARN from stack outputs
TASK_DEF=$(aws cloudformation describe-stacks \
  --stack-name TicketingLoadTestStack \
  --query 'Stacks[0].Outputs[?OutputKey==`TaskDefinitionArn`].OutputValue' \
  --output text)

# Get cluster name
CLUSTER=$(aws cloudformation describe-stacks \
  --stack-name TicketingLoadTestStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ClusterName`].OutputValue' \
  --output text)

# Run load test (adjust parameters as needed)
aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "loadtest",
      "command": [
        "./loadtest",
        "-requests", "50000",
        "-concurrency", "500",
        "-clients", "10",
        "-event", "1",
        "-mode", "best_available",
        "-quantity", "2"
      ]
    }]
  }'
```

### View Results

```bash
# Get results bucket name
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name TicketingLoadTestStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ResultsBucket`].OutputValue' \
  --output text)

# List test runs
aws s3 ls s3://$BUCKET/

# Download latest results
aws s3 cp s3://$BUCKET/<timestamp>/ ./results/ --recursive
```

## Cleanup

⚠️ **WARNING**: This deletes all data!

```bash
# Delete all stacks (creates snapshots)
uv run cdk destroy --all

# Manual cleanup
aws ecr delete-repository --repository-name ticketing-service --force
aws ecr delete-repository --repository-name seat-reservation-service --force
aws ecr delete-repository --repository-name loadtest-runner --force
aws s3 rb s3://<results-bucket> --force
```

## Related Documentation

- [Load Test Tool](../script/go_client/README.md) - Detailed loadtest usage
- [Test Specification](TEST_SPEC.md) - Testing strategy
- [Kafka Specification](KAFKA_SPEC.md) - Event-driven architecture
- [Kvrocks Specification](KVROCKS_SPEC.md) - Caching layer

## References

- [Aurora Serverless v2](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html)
- [Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html)
- [ECS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/welcome.html)
- [CDK API Reference](https://docs.aws.amazon.com/cdk/api/v2/)
