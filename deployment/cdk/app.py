#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
Manages API Gateway and routing configuration for LocalStack and AWS
"""

import os
from pathlib import Path

import aws_cdk as cdk
import yaml

from stacks.api_service_stack import APIServiceStack
from stacks.aurora_stack import AuroraStack
from stacks.ec2_kafka_stack import EC2KafkaStack
from stacks.ec2_kvrocks_stack import EC2KvrocksStack
from stacks.loadtest_stack import LoadTestStack
from stacks.reservation_consumer_stack import ReservationConsumerStack
from stacks.ticketing_consumer_stack import TicketingConsumerStack

app = cdk.App()

# ============= Load Configuration from YAML =============
# Read deployment/config.yml for environment-specific settings
config_path = Path(__file__).parent.parent / 'config.yml'
with open(config_path) as f:
    all_config = yaml.safe_load(f)

# Determine environment (default: production)
deploy_env = os.getenv('DEPLOY_ENV', 'production')
config = all_config[deploy_env]

print(f'📋 Loading configuration for environment: {deploy_env}')
print(f'   Region: {config["region"]}')
print(f'   ECS Tasks: {config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]}')
print(f'   Aurora ACU: {config["aurora"]["min_acu"]}-{config["aurora"]["max_acu"]}')

# Determine deployment target (LocalStack vs AWS)
is_localstack = os.getenv('CDK_DEFAULT_ACCOUNT') == '000000000000'

# Environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT', '000000000000'),
    region=os.getenv('CDK_DEFAULT_REGION', config['region']),
)

# ============= AWS Production Deployment (10000 TPS) =============
if not is_localstack:
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
    # Single instance for cost optimization
    # Cost: ~$12/month (vs ECS+EFS $25/month - saves $13/month!)
    kvrocks_stack = EC2KvrocksStack(
        app,
        'TicketingKvrocksStack',
        vpc=aurora_stack.vpc,
        config=config,
        env=env,
        description='Self-hosted Kvrocks on EC2 with EBS persistence',
    )
    kvrocks_stack.add_dependency(aurora_stack)

    # 4. API Service Stack (Unified Ticketing + Seat Reservation)
    api_stack = APIServiceStack(
        app,
        'APIServiceStack',
        vpc=aurora_stack.vpc,
        ecs_cluster=aurora_stack.ecs_cluster,
        alb_listener=aurora_stack.alb_listener,
        aurora_cluster_endpoint=aurora_stack.cluster_endpoint,
        aurora_cluster_secret=aurora_stack.cluster.secret,
        app_secrets=aurora_stack.app_secrets,
        namespace=aurora_stack.namespace,
        kafka_bootstrap_servers=kafka_stack.bootstrap_servers,
        kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,
        config=config,
        env=env,
        description=f'API Service on ECS Fargate ({config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks)',
    )
    api_stack.add_dependency(aurora_stack)
    api_stack.add_dependency(kvrocks_stack)
    api_stack.add_dependency(kafka_stack)

    # 5. Ticketing Consumer Stack (Background Kafka consumer)
    ticketing_consumer_stack = TicketingConsumerStack(
        app,
        'TicketingConsumerStack',
        vpc=aurora_stack.vpc,
        ecs_cluster=aurora_stack.ecs_cluster,
        aurora_cluster_endpoint=aurora_stack.cluster_endpoint,
        aurora_cluster_secret=aurora_stack.cluster.secret,
        app_secrets=aurora_stack.app_secrets,
        namespace=aurora_stack.namespace,
        kafka_bootstrap_servers=kafka_stack.bootstrap_servers,
        kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,
        config=config,
        env=env,
        description=f'Ticketing Consumer on ECS Fargate ({config.get("consumers", {}).get("ticketing", {}).get("min_tasks", 50)}-{config.get("consumers", {}).get("ticketing", {}).get("max_tasks", 100)} tasks)',
    )
    ticketing_consumer_stack.add_dependency(aurora_stack)
    ticketing_consumer_stack.add_dependency(kvrocks_stack)
    ticketing_consumer_stack.add_dependency(kafka_stack)

    # 6. Seat Reservation Consumer Stack (Background Kafka consumer + Kvrocks polling)
    reservation_consumer_stack = ReservationConsumerStack(
        app,
        'ReservationConsumerStack',
        vpc=aurora_stack.vpc,
        ecs_cluster=aurora_stack.ecs_cluster,
        aurora_cluster_secret=aurora_stack.cluster.secret,
        app_secrets=aurora_stack.app_secrets,
        namespace=aurora_stack.namespace,
        kafka_bootstrap_servers=kafka_stack.bootstrap_servers,
        kvrocks_endpoint=kvrocks_stack.kvrocks_endpoint,
        config=config,
        env=env,
        description=f'Reservation Consumer on ECS Fargate ({config.get("consumers", {}).get("reservation", {}).get("min_tasks", 50)}-{config.get("consumers", {}).get("reservation", {}).get("max_tasks", 100)} tasks)',
    )
    reservation_consumer_stack.add_dependency(aurora_stack)
    reservation_consumer_stack.add_dependency(kvrocks_stack)
    reservation_consumer_stack.add_dependency(kafka_stack)

    # 7. Load Test Stack (optional - for performance testing)
    loadtest_cpu = config.get('loadtest', {}).get('task_cpu', 2048)
    loadtest_mem = config.get('loadtest', {}).get('task_memory', 4096)
    loadtest_stack = LoadTestStack(
        app,
        'TicketingLoadTestStack',
        vpc=aurora_stack.vpc,
        ecs_cluster=aurora_stack.ecs_cluster,  # Use shared cluster
        alb_dns=aurora_stack.alb.load_balancer_dns_name,  # Internal DNS (free traffic)
        config=config,  # Pass config for CPU/Memory settings
        env=env,
        description=f'[Optional] Load test runner on Fargate Spot ({loadtest_cpu} CPU + {loadtest_mem}MB RAM)',
    )
    loadtest_stack.add_dependency(api_stack)

    print('✅ Deploying to AWS (Cost-Optimized Architecture):')
    print('   1. Database: Aurora Serverless v2 (0.5-64 ACU, single master)')
    print('   2. Messaging: EC2 Kafka (3 brokers on t3.xlarge with Docker) 💰 SAVES $337/mo')
    print('   3. Cache: Kvrocks on ECS (single master with EFS persistence)')
    print('   4. API Service: ECS Fargate (1-4 tasks, unified ticketing + reservation)')
    print('   5. Consumers: ECS Fargate (100-200 tasks total, background workers)')
    print('   6. Load Balancer: Application Load Balancer')
    print('')
    print('💰 Estimated Monthly Cost (at max scale):')
    print('   - Kafka EC2: t3.xlarge + 100GB EBS = ~$129/month (vs MSK $466)')
    print('   - API Service: 4 tasks × 8 vCPU = 32 vCPU (~$50/month)')
    print('   - Consumers: 200 tasks × 1 vCPU = 200 vCPU (~$300/month)')
    print('   - Total Infrastructure: ~$480/month (vs $817 with MSK)')
    print('   💵 MONTHLY SAVINGS: $337 (41% reduction!)')
    print('')
    print('⚡ Capacity: 10,000+ TPS with 200 consumer workers')
    print('🔒 Reliability: 3-broker Kafka cluster with replication factor 3')

# ============= LocalStack Development =============
else:
    print('⚠️  LocalStack deployment not configured.')
    print('   Use docker-compose for local development instead.')

app.synth()
