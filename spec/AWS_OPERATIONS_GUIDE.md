# AWS Operations Guide

## Infrastructure IDs

```bash
# Kafka EC2 Instances
KAFKA_INSTANCES="i-01de6aa1003e42e07 i-0d502954e59df5b62 i-07438e7245ec5308e"

# Kvrocks ASG
KVROCKS_ASG="TicketingKvrocksStack-KvrocksASGA62369E3-nmgIKdcLEJGz"
```

---

## Quick Start (Complete)

```bash
# 1. Start Kafka EC2 (3 brokers)
aws ec2 start-instances --instance-ids i-01de6aa1003e42e07 i-0d502954e59df5b62 i-07438e7245ec5308e

# 2. Start Kvrocks EC2 (ASG)
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name "TicketingKvrocksStack-KvrocksASGA62369E3-nmgIKdcLEJGz" \
  --desired-capacity 1

# 3. Wait for Kafka to be running
aws ec2 wait instance-running --instance-ids i-01de6aa1003e42e07 i-0d502954e59df5b62 i-07438e7245ec5308e

# 4. Push Docker images to ECR
./deployment/script/ecr-push.sh development all

# 5. Deploy CDK stacks
DEPLOY_ENV=development uv run cdk deploy --all

# 6. Seed data (optional)
make aws-seed
```

---

## Stop All (Save Cost)

```bash
# 1. Scale down ECS services
for svc in ticketing-development-ticketing-service ticketing-development-booking-service ticketing-development-reservation-service; do
  aws ecs update-service --cluster ticketing-cluster --service $svc --desired-count 0
done

# 2. Stop Kafka EC2
aws ec2 stop-instances --instance-ids i-01de6aa1003e42e07 i-0d502954e59df5b62 i-07438e7245ec5308e

# 3. Stop Kvrocks (ASG scale to 0)
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name "TicketingKvrocksStack-KvrocksASGA62369E3-nmgIKdcLEJGz" \
  --desired-capacity 0

# 4. Stop LoadTest EC2
LOADTEST_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=loadtest-*" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$LOADTEST_ID" != "None" ] && aws ec2 stop-instances --instance-ids $LOADTEST_ID
```

---

## Check Status

```bash
# All EC2 instances
aws ec2 describe-instances \
  --query 'Reservations[].Instances[].{Name:Tags[?Key==`Name`].Value|[0],State:State.Name,Id:InstanceId}' \
  --output table

# ECS services
aws ecs list-services --cluster ticketing-cluster --query 'serviceArns[*]' --output table

# Kvrocks ASG
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names "TicketingKvrocksStack-KvrocksASGA62369E3-nmgIKdcLEJGz" \
  --query 'AutoScalingGroups[0].{Desired:DesiredCapacity,Running:Instances[*].InstanceId}' \
  --output table
```

---

## Common Operations

### Restart ECS Services

```bash
# Restart all services (force new deployment)
for svc in ticketing-development-ticketing-service ticketing-development-booking-service ticketing-development-reservation-service; do
  aws ecs update-service --cluster ticketing-cluster --service $svc --force-new-deployment
done
```

### View Logs

```bash
aws logs tail /ecs/ticketing-development-ticketing-service --follow
aws logs tail /ecs/ticketing-development-booking-consumer --follow
aws logs tail /ecs/ticketing-development-reservation-consumer --follow
```

### SSM Connect to EC2

```bash
# Connect to Kafka broker
aws ssm start-session --target i-01de6aa1003e42e07

# Connect to LoadTest instance (get ID first)
LOADTEST_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=loadtest-*" --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ssm start-session --target $LOADTEST_ID
```

### Reset Kafka Topics

```bash
# Get Kafka instance ID
KAFKA_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=kafka-broker-1" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

# Delete and recreate topics via SSM
aws ssm send-command --instance-ids $KAFKA_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /opt/kafka",
    "docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic ticketing-events || true",
    "docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --delete --topic seat-reservation-events || true",
    "docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic ticketing-events --partitions 100 --replication-factor 3",
    "docker-compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --create --topic seat-reservation-events --partitions 100 --replication-factor 3"
  ]'
```

---

## Update Code & Redeploy

```bash
# 1. Push new Docker images
./deployment/script/ecr-push.sh development all

# 2. Force new deployment
for svc in ticketing-development-ticketing-service ticketing-development-booking-service ticketing-development-reservation-service; do
  aws ecs update-service --cluster ticketing-cluster --service $svc --force-new-deployment
done
```

---

## Troubleshooting

### Service not starting

```bash
# Check ECS events
aws ecs describe-services --cluster ticketing-cluster \
  --services ticketing-development-ticketing-service \
  --query 'services[0].events[0:5]'
```

### Kafka connection issues

```bash
# Check Kafka containers
aws ssm send-command --instance-ids i-01de6aa1003e42e07 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'
```

### Aurora status

```bash
aws rds describe-db-clusters \
  --db-cluster-identifier ticketing-aurora-cluster \
  --query 'DBClusters[0].Status'
```

---
