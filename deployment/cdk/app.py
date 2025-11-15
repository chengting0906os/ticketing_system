#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
Manages API Gateway and routing configuration for LocalStack and AWS
"""

import os
from pathlib import Path

import aws_cdk as cdk
from stacks.aurora_stack import AuroraStack
from stacks.booking_service_stack import BookingServiceStack
from stacks.ec2_kafka_stack import EC2KafkaStack
from stacks.ec2_kvrocks_stack import EC2KvrocksStack
from stacks.loadtest_stack import LoadTestStack
from stacks.reservation_service_stack import ReservationServiceStack
from stacks.ticketing_service_stack import TicketingServiceStack
import yaml


app = cdk.App()

# ============= Load Configuration from YAML =============
# Read deployment/config.yml for environment-specific settings
config_path = Path(__file__).parent.parent / 'config.yml'
with open(config_path) as f:
    all_config = yaml.safe_load(f)

# Determine environment (default: production)
deploy_env = os.getenv('DEPLOY_ENV', 'development')
config = all_config[deploy_env]

print(f'📋 Loading configuration for environment: {deploy_env}')
print(f'   Region: {config["region"]}')
print(f'   ECS Tasks: {config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]}')
print(f'   Aurora ACU: {config["aurora"]["min_acu"]}-{config["aurora"]["max_acu"]}')

# Environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', config['region']),
)

# ============= AWS Deployment (10000 TPS) =============
# 1. Aurora Serverless v2 Stack (Database + VPC)
# Single master (1 writer only), auto-scaling from config.yml ACU settings
# Creates VPC that will be shared by all other stacks
aurora_stack = AuroraStack(
    app,
    'TicketingAuroraStack',
    env=env,
    min_capacity=config['aurora']['min_acu'],
    max_capacity=config['aurora']['max_acu'],
    description=f'Aurora Serverless v2 ({config["aurora"]["min_acu"]}-{config["aurora"]["max_acu"]} ACU)',
)

# 2. EC2 Kafka Stack (Self-hosted Kafka on single EC2 instance)
# 3 brokers running in Docker containers with KRaft mode
# Cost: ~$129/month (vs MSK $466/month - saves $337/month!)
kafka_stack = EC2KafkaStack(
    app,
    'TicketingKafkaStack',
    vpc=aurora_stack.vpc,
    config=config,
    env=env,
    description='Self-hosted Kafka cluster on EC2 with Docker Compose (3 brokers)',
)
kafka_stack.add_dependency(aurora_stack)

# 3. EC2 Kvrocks Stack (Self-hosted Redis alternative on EC2)
# EC2 instance running Kvrocks binary from kvrocks-fpm (pre-compiled .deb)
# Cost: ~$12/month (t3.small + EBS) - fast deployment, no compilation needed
kvrocks_stack = EC2KvrocksStack(
    app,
    'TicketingKvrocksStack',
    vpc=aurora_stack.vpc,
    namespace=aurora_stack.namespace,
    config=config,
    env=env,
    description='Self-hosted Kvrocks on EC2 (kvrocks-fpm v2.13.0-1 amd64)',
)
kvrocks_stack.add_dependency(aurora_stack)

# 4. Ticketing API Service Stack (API Only)
# Handles HTTP API endpoints for user authentication, events, and bookings
# Kafka consumers run as separate ECS services for better scalability
# - API service: Read-only access to Kvrocks for availability checks
# - Consumers: Run independently, process Kafka events, update Kvrocks
ticketing_service_stack = TicketingServiceStack(
    app,
    'TicketingServiceStack',
    vpc=aurora_stack.vpc,
    ecs_cluster=aurora_stack.ecs_cluster,
    alb_listener=aurora_stack.alb_listener,
    aurora_cluster_endpoint=aurora_stack.cluster_endpoint,
    aurora_cluster_secret=aurora_stack.cluster.secret,
    app_secrets=aurora_stack.app_secrets,
    namespace=aurora_stack.namespace,
    kafka_bootstrap_servers=kafka_stack.bootstrap_servers,
    kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,
    kvrocks_security_group=kvrocks_stack.security_group,
    config=config,
    env=env,
    description=f'Ticketing API Service on ECS Fargate ({config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks)',
)
ticketing_service_stack.add_dependency(aurora_stack)
ticketing_service_stack.add_dependency(kvrocks_stack)
ticketing_service_stack.add_dependency(kafka_stack)

# 5. Booking Consumer Service Stack (Background Kafka consumer)
# Processes booking confirmations and seat allocations from Kafka topics
# - Reads from Kafka topics: seat.reserved.confirmed
# - Updates PostgreSQL with booking confirmations
# - Independent scaling from API service
booking_service_stack = BookingServiceStack(
    app,
    'BookingServiceStack',
    vpc=aurora_stack.vpc,
    ecs_cluster=aurora_stack.ecs_cluster,
    aurora_cluster_secret=aurora_stack.cluster.secret,
    aurora_cluster_endpoint=aurora_stack.cluster_endpoint,
    app_secrets=aurora_stack.app_secrets,
    namespace=aurora_stack.namespace,
    kafka_bootstrap_servers=kafka_stack.bootstrap_servers,
    kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,
    kvrocks_security_group=kvrocks_stack.security_group,
    config=config,
    env=env,
    description=f'Booking Consumer Service on ECS Fargate ({config.get("consumers", {}).get("booking", {}).get("min_tasks", 2)}-{config.get("consumers", {}).get("booking", {}).get("max_tasks", 4)} tasks)',
)
booking_service_stack.add_dependency(aurora_stack)
booking_service_stack.add_dependency(kafka_stack)
booking_service_stack.add_dependency(kvrocks_stack)

# 6. Reservation Service Stack (Background Kafka consumer + Kvrocks polling)
reservation_service_stack = ReservationServiceStack(
    app,
    'ReservationServiceStack',
    vpc=aurora_stack.vpc,
    ecs_cluster=aurora_stack.ecs_cluster,
    aurora_cluster_secret=aurora_stack.cluster.secret,
    app_secrets=aurora_stack.app_secrets,
    namespace=aurora_stack.namespace,
    kafka_bootstrap_servers=kafka_stack.bootstrap_servers,
    kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,
    kvrocks_security_group=kvrocks_stack.security_group,
    config=config,
    env=env,
    description=f'Seat Reservation Service on ECS Fargate ({config.get("consumers", {}).get("reservation", {}).get("min_tasks", 50)}-{config.get("consumers", {}).get("reservation", {}).get("max_tasks", 100)} tasks)',
)
reservation_service_stack.add_dependency(aurora_stack)
reservation_service_stack.add_dependency(kvrocks_stack)
reservation_service_stack.add_dependency(kafka_stack)

# 7. Load Test Stack (optional - for performance testing + interactive operations)
loadtest_cpu = config.get('loadtest', {}).get('task_cpu', 2048)
loadtest_mem = config.get('loadtest', {}).get('task_memory', 4096)
loadtest_stack = LoadTestStack(
    app,
    'TicketingLoadTestStack',
    vpc=aurora_stack.vpc,
    ecs_cluster=aurora_stack.ecs_cluster,  # Use shared cluster
    alb_dns=aurora_stack.alb.load_balancer_dns_name,  # Internal DNS (free traffic)
    aurora_cluster_endpoint=aurora_stack.cluster_endpoint,  # For seed operations
    aurora_cluster_secret=aurora_stack.cluster.secret,  # Aurora credentials
    app_secrets=aurora_stack.app_secrets,  # JWT secrets
    kafka_bootstrap_servers=kafka_stack.bootstrap_servers,  # Kafka endpoints
    kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,  # Kvrocks endpoint
    config=config,  # Pass config for CPU/Memory settings
    env=env,
    description=f'[Optional] Load test + interactive ops on Fargate ({loadtest_cpu} CPU + {loadtest_mem}MB RAM)',
)
loadtest_stack.add_dependency(ticketing_service_stack)
loadtest_stack.add_dependency(kafka_stack)
loadtest_stack.add_dependency(kvrocks_stack)

app.synth()
