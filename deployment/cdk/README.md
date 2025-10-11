# AWS CDK Infrastructure for Ticketing System

This directory contains AWS CDK code to manage infrastructure as code using Python.

## Structure

```
infrastructure/cdk/
├── app.py                      # CDK app entry point
├── cdk.json                    # CDK configuration
├── stacks/
│   ├── __init__.py
│   └── api_gateway_stack.py   # API Gateway configuration
└── README.md
```

## Quick Start

### 1. Install CDK CLI (if not already installed)

```bash
npm install -g aws-cdk
```

### 2. Deploy to LocalStack

```bash
# Set LocalStack endpoint
export CDK_DEFAULT_ACCOUNT=000000000000
export CDK_DEFAULT_REGION=us-east-1

# Bootstrap CDK (first time only)
cdklocal bootstrap

# Deploy the stack
cdklocal deploy
```

### 3. Deploy to AWS (Production)

```bash
# Configure AWS credentials first
aws configure

# Bootstrap CDK for your AWS account (first time only)
cdk bootstrap

# Deploy to AWS
cdk deploy
```

## Available Commands

- `cdk synth` - Synthesize CloudFormation template
- `cdk diff` - Show differences between deployed and local
- `cdk deploy` - Deploy stack to AWS
- `cdk destroy` - Remove all resources
- `cdklocal deploy` - Deploy to LocalStack (local development)

## Architecture

The CDK stack creates:

- **API Gateway REST API** with routes:
  - `/api/user/*` → Ticketing Service (port 8000)
  - `/api/event/*` → Ticketing Service (port 8000)
  - `/api/booking/*` → Ticketing Service (port 8000)
  - `/api/seat-reservation/*` → Seat Reservation Service (port 8001)

Each route supports:
- Base path (e.g., `/api/event`)
- Sub-paths (e.g., `/api/event/1`, `/api/event/1/seats`)

## Benefits of CDK over Bash Scripts

1. **Type Safety**: Python type hints catch errors before deployment
2. **Reusability**: Create reusable constructs for common patterns
3. **Testing**: Unit test your infrastructure code
4. **IDE Support**: Autocomplete and documentation in your editor
5. **Multi-Environment**: Same code deploys to LocalStack and AWS
6. **State Management**: CDK tracks what's deployed and only updates changes

## Example: Testing Before Deploy

```python
# You can write tests for your infrastructure!
def test_api_gateway_has_correct_routes():
    stack = ApiGatewayStack(app, "test")
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::ApiGateway::RestApi", 1)
    template.has_resource_properties("AWS::ApiGateway::Resource", {
        "PathPart": "event"
    })
```
