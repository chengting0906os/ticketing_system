#!/bin/bash
# Deploy ScyllaDB Stack to AWS
# Usage: ./deploy-scylla.sh [environment]
# Example: ./deploy-scylla.sh development

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CDK_DIR="$PROJECT_ROOT/deployment/cdk"

# Environment (default: development)
DEPLOY_ENV="${1:-development}"

# Validate environment
if [[ ! "$DEPLOY_ENV" =~ ^(development|staging|production)$ ]]; then
    echo "❌ Invalid environment: $DEPLOY_ENV"
    echo "   Valid options: development, staging, production"
    exit 1
fi

# ============================================================================
# AWS Configuration
# ============================================================================
echo "🔧 Configuring AWS environment..."

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="${AWS_DEFAULT_REGION:-us-west-2}"

echo "   Account: $AWS_ACCOUNT_ID"
echo "   Region: $AWS_REGION"
echo "   Environment: $DEPLOY_ENV"

# Set CDK environment variables
export CDK_DEFAULT_ACCOUNT="$AWS_ACCOUNT_ID"
export CDK_DEFAULT_REGION="$AWS_REGION"
export DEPLOY_ENV="$DEPLOY_ENV"

# ============================================================================
# Prerequisites Check
# ============================================================================
echo ""
echo "🔍 Checking prerequisites..."

# Check AWS credentials
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS credentials not configured"
    echo "   Run: aws configure"
    exit 1
fi

# Check CDK
if ! command -v cdk &> /dev/null; then
    echo "❌ AWS CDK not installed"
    echo "   Run: npm install -g aws-cdk"
    exit 1
fi

echo "✅ Prerequisites check passed"

# ============================================================================
# CDK Bootstrap (if needed)
# ============================================================================
echo ""
echo "🚀 Checking CDK bootstrap..."

if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "   CDK not bootstrapped. Bootstrapping now..."
    cd "$CDK_DIR"
    cdk bootstrap "aws://$AWS_ACCOUNT_ID/$AWS_REGION"
else
    echo "   CDK already bootstrapped"
fi

# ============================================================================
# Synthesize CDK Stack
# ============================================================================
echo ""
echo "📦 Synthesizing CDK stack..."
cd "$CDK_DIR"

if ! cdk synth TicketingScyllaStack > /dev/null 2>&1; then
    echo "❌ CDK synthesis failed"
    exit 1
fi

echo "✅ CDK synthesis successful"

# ============================================================================
# Show Configuration Summary
# ============================================================================
echo ""
echo "=========================================="
echo "  ScyllaDB Deployment Configuration"
echo "=========================================="

# Parse config.yml to show ScyllaDB settings
python3 <<EOF
import yaml
from pathlib import Path

config_path = Path("$PROJECT_ROOT/deployment/config.yml")
with open(config_path) as f:
    config = yaml.safe_load(f)["$DEPLOY_ENV"]

scylla_config = config.get("scylla", {})
node_count = scylla_config.get("node_count", 3)
instance_type = scylla_config.get("instance_type", "i3.xlarge")
use_spot = scylla_config.get("use_spot_instances", False)

print(f"  Node Count:       {node_count}")
print(f"  Instance Type:    {instance_type}")
print(f"  Spot Instances:   {'Yes' if use_spot else 'No'}")

# Estimate cost
if instance_type == "t3.xlarge":
    hourly_cost = 0.1664 * node_count
    monthly_cost = hourly_cost * 730
elif instance_type == "i3.xlarge":
    hourly_cost = (0.312 if not use_spot else 0.0936) * node_count
    monthly_cost = hourly_cost * 730
else:
    hourly_cost = 0
    monthly_cost = 0

print(f"  Est. Cost:        \${monthly_cost:.2f}/month")
print("==========================================")
EOF

# ============================================================================
# Confirmation Prompt
# ============================================================================
echo ""
read -p "⚠️  Deploy ScyllaDB stack to AWS? (yes/no): " CONFIRM

if [[ "$CONFIRM" != "yes" ]]; then
    echo "❌ Deployment cancelled"
    exit 0
fi

# ============================================================================
# Deploy Stack
# ============================================================================
echo ""
echo "🚀 Deploying TicketingScyllaStack..."
echo ""

cd "$CDK_DIR"
cdk deploy TicketingScyllaStack \
    --require-approval never \
    --outputs-file cdk-scylla-outputs.json

# ============================================================================
# Post-Deployment
# ============================================================================
echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="

if [ -f "$CDK_DIR/cdk-scylla-outputs.json" ]; then
    echo ""
    echo "📋 Stack Outputs:"
    cat "$CDK_DIR/cdk-scylla-outputs.json" | python3 -m json.tool
fi

echo ""
echo "🔗 Next Steps:"
echo ""
echo "1. Wait for ScyllaDB nodes to initialize (~5-10 minutes)"
echo "   Check status: aws ssm start-session --target <instance-id>"
echo "   Then run: nodetool status"
echo ""
echo "2. Connect to ScyllaDB from application:"
echo "   Set SCYLLA_CONTACT_POINTS environment variable to node IPs"
echo ""
echo "3. Monitor cluster:"
echo "   CloudWatch Logs: /aws/scylla/ticketing-scylla-cluster"
echo "   Prometheus metrics: http://<node-ip>:9180/metrics"
echo ""
echo "4. Verify schema:"
echo "   cqlsh <node-ip>"
echo "   DESCRIBE KEYSPACE ticketing_system;"
echo ""
echo "=========================================="
