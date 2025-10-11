#!/usr/bin/env python3
"""
AWS CDK App for Ticketing System Infrastructure
Manages API Gateway and routing configuration for LocalStack and AWS
"""

import os

import aws_cdk as cdk

from stacks.api_gateway_stack import ApiGatewayStack
from stacks.database_stack import DatabaseStack

app = cdk.App()

# Determine deployment target (LocalStack vs AWS)
is_localstack = os.getenv('CDK_DEFAULT_ACCOUNT') == '000000000000'

# Create API Gateway Stack
ApiGatewayStack(
    app,
    'TicketingApiGatewayStack',
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT', '000000000000'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1'),
    ),
    description='API Gateway for Ticketing System microservices',
)

# Create Database Stack (AWS only - not supported in LocalStack)
if not is_localstack:
    DatabaseStack(
        app,
        'TicketingDatabaseStack',
        env=cdk.Environment(
            account=os.getenv('CDK_DEFAULT_ACCOUNT'),
            region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1'),
        ),
        description='RDS PostgreSQL database for Ticketing System',
    )
    print('⚠️  Note: Database stack will only deploy to real AWS, not LocalStack')
    print('   For local development, continue using docker-compose.yml')

app.synth()
