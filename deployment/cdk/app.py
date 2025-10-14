#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
Manages API Gateway and routing configuration for LocalStack and AWS
"""

import os

import aws_cdk as cdk

from stacks.api_gateway_stack import ApiGatewayStack
from stacks.database_stack import DatabaseStack
from stacks.load_balancer_stack import LoadBalancerStack, LoadBalancerStackForLocalStack
from stacks.msk_stack import MSKStack

app = cdk.App()

# Determine deployment target (LocalStack vs AWS)
is_localstack = os.getenv('CDK_DEFAULT_ACCOUNT') == '000000000000'

# Environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT', '000000000000'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1'),
)

# ============= AWS Production Deployment =============
if not is_localstack:
    # 1. Database Stack (RDS PostgreSQL)
    db_stack = DatabaseStack(
        app,
        'TicketingDatabaseStack',
        env=env,
        description='RDS PostgreSQL database for Ticketing System',
    )

    # 2. MSK Stack (Amazon Managed Streaming for Apache Kafka)
    # Note: Comment out this stack if you want to keep using docker-compose Kafka during development
    msk_stack = MSKStack(
        app,
        'TicketingMSKStack',
        vpc=db_stack.database.vpc,  # Reuse VPC from database stack
        env=env,
        description='Amazon MSK cluster for event-driven messaging',
    )
    msk_stack.add_dependency(db_stack)

    # 3. Load Balancer Stack (ALB)
    lb_stack = LoadBalancerStack(
        app,
        'TicketingLoadBalancerStack',
        vpc=db_stack.database.vpc,  # Reuse VPC from database stack
        env=env,
        description='Application Load Balancer for microservices',
    )
    # Ensure database is created before load balancer
    lb_stack.add_dependency(db_stack)

    # 4. API Gateway Stack (optional - can use ALB directly)
    # Note: In production, you might choose ALB OR API Gateway, not both
    # Keeping both for flexibility during migration
    api_stack = ApiGatewayStack(
        app,
        'TicketingApiGatewayStack',
        env=env,
        description='API Gateway for Ticketing System microservices',
    )

    print('✅ Deploying to AWS:')
    print('   - Database Stack: RDS PostgreSQL')
    print('   - MSK Stack: Amazon Managed Streaming for Apache Kafka')
    print('   - Load Balancer Stack: Application Load Balancer')
    print('   - API Gateway Stack: REST API')

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
