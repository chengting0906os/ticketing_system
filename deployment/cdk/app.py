#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
Manages API Gateway and routing configuration for LocalStack and AWS
"""

import os

import aws_cdk as cdk

from stacks.api_gateway_stack import ApiGatewayStack
from stacks.aurora_stack import AuroraStack
from stacks.database_stack import DatabaseStack
from stacks.ecs_stack import ECSStack
from stacks.kvrocks_stack import KvrocksStack
from stacks.load_balancer_stack import LoadBalancerStack, LoadBalancerStackForLocalStack
from stacks.loadtest_stack import LoadTestStack
from stacks.msk_stack import MSKStack

app = cdk.App()

# Determine deployment target (LocalStack vs AWS)
is_localstack = os.getenv('CDK_DEFAULT_ACCOUNT') == '000000000000'

# Environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT', '000000000000'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1'),
)

# ============= AWS Production Deployment (10000 TPS) =============
if not is_localstack:
    # 1. Database Stack (Legacy RDS - kept for backward compatibility)
    # Consider migrating to Aurora stack for better scalability
    db_stack = DatabaseStack(
        app,
        'TicketingDatabaseStack',
        env=env,
        description='[Legacy] RDS PostgreSQL database for Ticketing System',
    )

    # 1b. Aurora Serverless v2 Stack (Recommended for production)
    # 1 writer + 1 reader, auto-scaling 2-64 ACU for 10000 TPS
    aurora_stack = AuroraStack(
        app,
        'TicketingAuroraStack',
        vpc=db_stack.database.vpc,  # Reuse VPC from database stack
        env=env,
        description='Aurora Serverless v2 PostgreSQL cluster (1 writer + 1 reader)',
    )
    aurora_stack.add_dependency(db_stack)

    # 2. MSK Stack (Amazon Managed Streaming for Apache Kafka)
    # 3-node cluster for event-driven messaging
    msk_stack = MSKStack(
        app,
        'TicketingMSKStack',
        vpc=db_stack.database.vpc,
        env=env,
        description='Amazon MSK cluster for event-driven messaging',
    )
    msk_stack.add_dependency(db_stack)

    # 3. ECS Cluster (Create first for Kvrocks to use)
    # Shared cluster for both microservices and Kvrocks
    from aws_cdk import aws_ecs as ecs

    shared_cluster = ecs.Cluster(
        db_stack,  # Create within database stack for VPC access
        'SharedECSCluster',
        cluster_name='ticketing-shared-cluster',
        vpc=db_stack.database.vpc,
        container_insights=True,
    )

    # 4. Kvrocks + Sentinel Stack (Self-hosted Redis alternative)
    # 1 master + 2 replicas + 3 sentinels for high availability
    kvrocks_stack = KvrocksStack(
        app,
        'TicketingKvrocksStack',
        vpc=db_stack.database.vpc,
        cluster=shared_cluster,
        env=env,
        description='Kvrocks cluster with Sentinel (1 master + 2 replicas)',
    )
    kvrocks_stack.add_dependency(db_stack)

    # 5. ECS Fargate Stack (Microservices)
    # ticketing-service + seat-reservation-service
    # Each service: 4-16 tasks with auto-scaling
    ecs_stack = ECSStack(
        app,
        'TicketingECSStack',
        vpc=db_stack.database.vpc,
        aurora_security_group=aurora_stack.db_security_group,
        msk_security_group=msk_stack.security_group,
        kvrocks_security_group=kvrocks_stack.kvrocks_security_group,
        env=env,
        description='ECS Fargate services for microservices (4-16 tasks each)',
    )
    ecs_stack.add_dependency(aurora_stack)
    ecs_stack.add_dependency(msk_stack)
    ecs_stack.add_dependency(kvrocks_stack)

    # 6. Load Balancer Stack (ALB - Optional if using ECS ALB)
    # Note: ECS stack already creates an ALB, this is redundant
    # Keeping for backward compatibility
    lb_stack = LoadBalancerStack(
        app,
        'TicketingLoadBalancerStack',
        vpc=db_stack.database.vpc,
        env=env,
        description='[Optional] Additional Load Balancer (ECS already has ALB)',
    )
    lb_stack.add_dependency(db_stack)

    # 7. Load Test Stack (optional - for performance testing)
    # Fargate Spot with 32GB RAM for running high-concurrency Go load tests
    loadtest_stack = LoadTestStack(
        app,
        'TicketingLoadTestStack',
        vpc=db_stack.database.vpc,
        alb_dns=ecs_stack.alb.load_balancer_dns_name,
        env=env,
        description='[Optional] Load test runner on Fargate Spot (32GB RAM)',
    )
    loadtest_stack.add_dependency(ecs_stack)

    print('✅ Deploying to AWS (10000 TPS Architecture):')
    print('   1. Database: Aurora Serverless v2 (2-64 ACU, 1 writer + 1 reader)')
    print('   2. Messaging: Amazon MSK (3-node Kafka cluster)')
    print('   3. Cache: Kvrocks on ECS (1 master + 2 replicas + 3 sentinels)')
    print('   4. Compute: ECS Fargate (2 services, 4-16 tasks each)')
    print('   5. Load Balancer: Application Load Balancer (built into ECS)')
    print('')
    print('💰 Estimated Monthly Cost: $1,500 - $3,000 (at moderate load)')
    print('⚡ Capacity: 10,000+ TPS with auto-scaling')
    print('🔒 High Availability: Multi-AZ with auto-failover')

# ============= LocalStack Development =============
else:
    # For LocalStack, only use API Gateway (simpler for local testing)
    ApiGatewayStack(
        app,
        'TicketingApiGatewayStack',
        env=env,
        description='API Gateway for Ticketing System microservices',
    )

    # Show note about LocalStack limitations
    LoadBalancerStackForLocalStack(
        app,
        'TicketingLoadBalancerStack',
        env=env,
        description='Load Balancer note for LocalStack',
    )

    print('✅ Deploying to LocalStack:')
    print('   - API Gateway Stack: REST API')
    print('⚠️  Note: Using docker-compose for database and load balancing')
    print('   - Database: docker-compose.yml (PostgreSQL)')
    print('   - Load Balancer: Consider adding nginx to docker-compose.yml')

app.synth()
