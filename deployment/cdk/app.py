#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
Manages API Gateway and routing configuration for LocalStack and AWS
"""

import os
from pathlib import Path

import aws_cdk as cdk
import yaml

from stacks.aurora_stack import AuroraStack
from stacks.kvrocks_stack import KvrocksStack
from stacks.loadtest_stack import LoadTestStack
from stacks.msk_stack import MSKStack
from stacks.reservation_service_stack import ReservationServiceStack
from stacks.ticketing_service_stack import TicketingServiceStack

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

    # 2. MSK Stack (Amazon Managed Streaming for Apache Kafka)
    # 3-node cluster for event-driven messaging
    msk_stack = MSKStack(
        app,
        'TicketingMSKStack',
        vpc=aurora_stack.vpc,
        env=env,
        description='Amazon MSK cluster for event-driven messaging',
    )
    msk_stack.add_dependency(aurora_stack)

    # 3. Kvrocks Stack (Self-hosted Redis alternative)
    # Single master configuration for cost optimization
    kvrocks_stack = KvrocksStack(
        app,
        'TicketingKvrocksStack',
        vpc=aurora_stack.vpc,
        cluster=aurora_stack.ecs_cluster,
        namespace=aurora_stack.namespace,
        env=env,
        description='Kvrocks single master on ECS with EFS persistence',
    )
    kvrocks_stack.add_dependency(aurora_stack)

    # 4. Ticketing Service Stack (Independent deployment)
    ticketing_stack = TicketingServiceStack(
        app,
        'TicketingServiceStack',
        vpc=aurora_stack.vpc,
        ecs_cluster=aurora_stack.ecs_cluster,
        alb_listener=aurora_stack.alb_listener,
        aurora_cluster_endpoint=aurora_stack.cluster_endpoint,
        aurora_cluster_secret=aurora_stack.cluster.secret,
        namespace=aurora_stack.namespace,
        config=config,
        env=env,
        description=f'Ticketing Service on ECS Fargate ({config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks)',
    )
    ticketing_stack.add_dependency(aurora_stack)
    ticketing_stack.add_dependency(kvrocks_stack)

    # 5. Seat Reservation Service Stack (Independent deployment)
    reservation_stack = ReservationServiceStack(
        app,
        'ReservationServiceStack',
        vpc=aurora_stack.vpc,
        ecs_cluster=aurora_stack.ecs_cluster,
        alb_listener=aurora_stack.alb_listener,
        aurora_cluster_endpoint=aurora_stack.cluster_endpoint,
        aurora_cluster_secret=aurora_stack.cluster.secret,
        namespace=aurora_stack.namespace,
        config=config,
        env=env,
        description=f'Seat Reservation Service on ECS Fargate ({config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks)',
    )
    reservation_stack.add_dependency(aurora_stack)
    reservation_stack.add_dependency(kvrocks_stack)

    # 6. Load Test Stack (optional - for performance testing)
    loadtest_stack = LoadTestStack(
        app,
        'TicketingLoadTestStack',
        vpc=aurora_stack.vpc,
        alb_dns=aurora_stack.alb.load_balancer_dns_name,
        env=env,
        description='[Optional] Load test runner on Fargate Spot (32GB RAM)',
    )
    loadtest_stack.add_dependency(ticketing_stack)
    loadtest_stack.add_dependency(reservation_stack)

    print('✅ Deploying to AWS (10000 TPS Architecture):')
    print('   1. Database: Aurora Serverless v2 (2-64 ACU, single master)')
    print('   2. Messaging: Amazon MSK (3-broker Kafka cluster with KRaft)')
    print('   3. Cache: Kvrocks on ECS (single master with EFS persistence)')
    print('   4. Compute: ECS Fargate (2 services, 4-16 tasks each)')
    print('   5. Load Balancer: Application Load Balancer (built into ECS)')
    print('')
    print('💰 Estimated Monthly Cost: $1,500 - $3,000 (at moderate load)')
    print('⚡ Capacity: 10,000+ TPS with auto-scaling')
    print('🔒 High Availability: Multi-AZ with auto-failover')

# ============= LocalStack Development =============
else:
    print('⚠️  LocalStack deployment not configured.')
    print('   Use docker-compose for local development instead.')

app.synth()
