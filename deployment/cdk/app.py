#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
ScyllaDB-first architecture without Aurora dependency
"""

import os
from pathlib import Path

import aws_cdk as cdk
import yaml

from stacks.ecs_base_stack import ECSBaseStack
from stacks.kvrocks_stack import KvrocksStack
from stacks.msk_stack import MSKStack
from stacks.reservation_service_stack import ReservationServiceStack
from stacks.scylla_stack import ScyllaStack
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

scylla_config = config.get('scylla', {})
print(f'📋 Loading configuration for environment: {deploy_env}')
print(f'   Region: {config["region"]}')
print(
    f'   ScyllaDB: {scylla_config.get("node_count", 1)}-node {scylla_config.get("instance_type", "t3.xlarge")}'
)
print(f'   ECS Tasks: {config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]}')

# Determine deployment target (LocalStack vs AWS)
is_localstack = os.getenv('CDK_DEFAULT_ACCOUNT') == '000000000000'

# Environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT', '000000000000'),
    region=os.getenv('CDK_DEFAULT_REGION', config['region']),
)

# ============= AWS Production Deployment (ScyllaDB-first) =============
if not is_localstack:
    # 1. ScyllaDB Stack (Primary Database + VPC)
    # Creates VPC that will be shared by all other stacks
    # ScyllaDB as the primary data store for high-throughput, low-latency operations
    scylla_stack = ScyllaStack(
        app,
        'TicketingScyllaStack',
        vpc=None,  # ScyllaDB stack creates VPC
        node_count=scylla_config.get('node_count', 1),
        instance_type=scylla_config.get('instance_type', 't3.xlarge'),
        use_spot_instances=scylla_config.get('use_spot_instances', False),
        environment=deploy_env,
        env=env,
        description=f'ScyllaDB {scylla_config.get("node_count", 1)}-node cluster on EC2 (primary database)',
    )

    # 2. ECS Base Stack (ECS Cluster + ALB + Service Discovery)
    # Provides shared infrastructure for application services
    ecs_base_stack = ECSBaseStack(
        app,
        'TicketingECSBaseStack',
        vpc=scylla_stack.vpc,
        env=env,
        description='ECS Cluster, ALB, and Service Discovery for application services',
    )
    ecs_base_stack.add_dependency(scylla_stack)

    # 3. MSK Stack (Amazon Managed Streaming for Apache Kafka)
    # 3-node cluster for event-driven messaging
    msk_stack = MSKStack(
        app,
        'TicketingMSKStack',
        vpc=scylla_stack.vpc,
        env=env,
        description='Amazon MSK cluster for event-driven messaging',
    )
    msk_stack.add_dependency(scylla_stack)

    # 4. Kvrocks Stack (Self-hosted Redis alternative)
    # Single master configuration for distributed locking and caching
    kvrocks_stack = KvrocksStack(
        app,
        'TicketingKvrocksStack',
        vpc=scylla_stack.vpc,
        cluster=ecs_base_stack.ecs_cluster,
        namespace=ecs_base_stack.namespace,
        env=env,
        description='Kvrocks single master on ECS with EFS persistence',
    )
    kvrocks_stack.add_dependency(ecs_base_stack)

    # 5. Ticketing Service Stack (REST API for tickets, events, bookings)
    ticketing_stack = TicketingServiceStack(
        app,
        'TicketingServiceStack',
        vpc=scylla_stack.vpc,
        ecs_cluster=ecs_base_stack.ecs_cluster,
        alb_listener=ecs_base_stack.alb_listener,
        scylla_contact_points=scylla_stack.contact_points,
        namespace=ecs_base_stack.namespace,
        config=config,
        env=env,
        description=f'Ticketing Service on ECS Fargate ({config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks)',
    )
    ticketing_stack.add_dependency(ecs_base_stack)
    ticketing_stack.add_dependency(scylla_stack)
    ticketing_stack.add_dependency(kvrocks_stack)

    # 6. Seat Reservation Service Stack (REST API for seat reservations)
    reservation_stack = ReservationServiceStack(
        app,
        'ReservationServiceStack',
        vpc=scylla_stack.vpc,
        ecs_cluster=ecs_base_stack.ecs_cluster,
        alb_listener=ecs_base_stack.alb_listener,
        scylla_contact_points=scylla_stack.contact_points,
        namespace=ecs_base_stack.namespace,
        config=config,
        env=env,
        description=f'Seat Reservation Service on ECS Fargate ({config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks)',
    )
    reservation_stack.add_dependency(ecs_base_stack)
    reservation_stack.add_dependency(scylla_stack)
    reservation_stack.add_dependency(kvrocks_stack)

    print('')
    print('=' * 60)
    print('✅ ScyllaDB-first Architecture - Complete Stack')
    print('=' * 60)
    print(f'1. Primary Database: ScyllaDB ({scylla_config.get("node_count", 1)}-node cluster)')
    print(f'   Instance Type: {scylla_config.get("instance_type", "t3.xlarge")}')
    print(f'   Spot Instances: {"Yes" if scylla_config.get("use_spot_instances", False) else "No"}')
    print('')
    print('2. Messaging: Amazon MSK (3-broker Kafka cluster with KRaft)')
    print('')
    print('3. Cache/Lock: Kvrocks on ECS (single master with EFS persistence)')
    print('')
    print('4. Application Services: ECS Fargate with ALB')
    print(
        f'   - Ticketing Service: {config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks'
    )
    print(
        f'   - Reservation Service: {config["ecs"]["min_tasks"]}-{config["ecs"]["max_tasks"]} tasks'
    )
    print('')
    print('=' * 60)
    print('📊 Key Features:')
    print('=' * 60)
    print('✓ ScyllaDB as primary database (sub-ms p99 latency)')
    print('✓ Native EC2 deployment (15-20% faster than Docker)')
    print('✓ Shard-per-core architecture (linear scalability)')
    print('✓ No connection pooling bottlenecks')
    print('✓ Complete application stack deployed')
    print('')
    print('💰 Estimated Monthly Cost:')
    scylla_monthly_cost = {
        't3.xlarge': 122 * scylla_config.get('node_count', 1),
        'i3.xlarge': (
            68 * scylla_config.get('node_count', 1)
            if scylla_config.get('use_spot_instances', False)
            else 228 * scylla_config.get('node_count', 1)
        ),
    }.get(scylla_config.get('instance_type', 't3.xlarge'), 122)
    print(f'   ScyllaDB: ~${scylla_monthly_cost}/month')
    print('   MSK: ~$150/month')
    print('   Kvrocks: ~$25/month')
    print('   ECS (2 services): ~$120/month')
    print('   ALB: ~$25/month')
    print(f'   Total: ~${scylla_monthly_cost + 320}/month')
    print('')
    print('=' * 60)
    print('🚀 Deployment:')
    print('=' * 60)
    print('Deploy all stacks:')
    print('   cdk deploy --all')
    print('')
    print('Or deploy individually:')
    print('   1. cdk deploy TicketingScyllaStack')
    print('   2. cdk deploy TicketingECSBaseStack TicketingMSKStack')
    print('   3. cdk deploy TicketingKvrocksStack')
    print('   4. cdk deploy TicketingServiceStack ReservationServiceStack')
    print('')
    print('=' * 60)

# ============= LocalStack Development =============
else:
    print('⚠️  LocalStack deployment not configured.')
    print('   Use docker-compose for local development instead.')

app.synth()
