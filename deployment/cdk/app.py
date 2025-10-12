#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure

High-throughput architecture for 10,000 QPS:
- Aurora PostgreSQL cluster (writer + 3 readers)
- ElastiCache Redis cluster (3 shards)
- ECS Fargate with auto-scaling (30-100 tasks)
- Application Load Balancer
- CloudWatch monitoring and alarms

Supports both LocalStack (development) and AWS (production) deployments.
"""

import os

import aws_cdk as cdk
from stacks.api_gateway_stack import ApiGatewayStack
from stacks.aurora_stack import AuroraStack
from stacks.ecs_stack import EcsStack
from stacks.kvrocks_stack import KVRocksStack
from stacks.load_balancer_stack import LoadBalancerStackForLocalStack
from stacks.vpc_stack import VpcStack


app = cdk.App()

# Determine deployment target (LocalStack vs AWS)
is_localstack = os.getenv('CDK_DEFAULT_ACCOUNT') == '000000000000'

# Get environment from context or default to production
environment = app.node.try_get_context('environment') or 'production'

# Environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT', '000000000000'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1'),
)

# ============= AWS Production Deployment =============
if not is_localstack:
    # 1. VPC Stack (Network Foundation)
    vpc_stack = VpcStack(
        app,
        f'TicketingVpcStack-{environment}',
        env=env,
        description=f'VPC and network infrastructure for {environment}',
    )

    # 2. Aurora PostgreSQL Cluster Stack (Optimized for 10K QPS)
    aurora_stack = AuroraStack(
        app,
        f'TicketingAuroraStack-{environment}',
        vpc=vpc_stack.vpc,
        db_security_group_id=vpc_stack.db_security_group.security_group_id,
        proxy_security_group_id=vpc_stack.proxy_security_group.security_group_id,
        app_security_group_id=vpc_stack.app_security_group.security_group_id,
        environment=environment,
        env=env,
        description=f'Aurora PostgreSQL cluster for {environment} (10K QPS)',
    )
    aurora_stack.add_dependency(vpc_stack)

    # 3. Self-Hosted KVRocks Stack (State Storage)
    kvrocks_stack = KVRocksStack(
        app,
        f'TicketingKVRocksStack-{environment}',
        vpc=vpc_stack.vpc,
        app_security_group_id=vpc_stack.app_security_group.security_group_id,
        environment=environment,
        env=env,
        description=f'Self-hosted KVRocks for {environment}',
    )
    kvrocks_stack.add_dependency(vpc_stack)

    # 4. ECS Fargate Stack (Application Layer)
    ecs_stack = EcsStack(
        app,
        f'TicketingEcsStack-{environment}',
        vpc=vpc_stack.vpc,
        cluster=kvrocks_stack.cluster,  # Shared ECS cluster
        app_security_group_id=vpc_stack.app_security_group.security_group_id,
        db_credentials_secret=aurora_stack.db_credentials_secret,
        db_proxy_endpoint=aurora_stack.proxy_endpoint,  # Writer endpoint (RDS Proxy)
        db_reader_endpoint=aurora_stack.reader_endpoint,  # Reader endpoint (read replicas)
        kvrocks_endpoint=kvrocks_stack.connection_string,
        environment=environment,
        env=env,
        description=f'ECS Fargate service for {environment} (10K QPS)',
    )
    ecs_stack.add_dependency(vpc_stack)
    ecs_stack.add_dependency(aurora_stack)
    ecs_stack.add_dependency(kvrocks_stack)

    # 4. API Gateway Stack (Optional - for development only)
    if environment != 'production':
        api_stack = ApiGatewayStack(
            app,
            f'TicketingApiGatewayStack-{environment}',
            env=env,
            description='API Gateway for Ticketing System microservices',
        )

# ============= LocalStack Development =============
else:
    # For LocalStack, only use API Gateway (simpler for local testing)
    # Note: Use docker-compose for database, Redis, and load balancer
    ApiGatewayStack(
        app,
        'TicketingApiGatewayStack',
        env=env,
        description='API Gateway for Ticketing System microservices',
    )

    LoadBalancerStackForLocalStack(
        app,
        'TicketingLoadBalancerStack',
        env=env,
        description='Load Balancer note for LocalStack',
    )

app.synth()
