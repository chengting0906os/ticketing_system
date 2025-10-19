#!/bin/bash
# =============================================================================
# AWS One-Click Destroy Script
# =============================================================================
# Purpose: Delete all AWS resources to stop billing
# Usage: make destroy  or  ./deployment/destroy-all.sh
# =============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# =============================================================================
# 1. Confirm Destruction
# =============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              ⚠️  DESTROYING AWS INFRASTRUCTURE ⚠️              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

log_warning "This will DELETE ALL deployed AWS resources:"
echo "  🗑️  Aurora Serverless v2 (DATABASE WILL BE DELETED!)"
echo "  🗑️  Amazon MSK (Kafka cluster)"
echo "  🗑️  Kvrocks on ECS"
echo "  🗑️  ECS Services (ticketing + seat-reservation)"
echo "  🗑️  Application Load Balancer"
echo "  🗑️  All associated Security Groups, VPC, etc."
echo ""

log_error "⚠️  ALL DATA WILL BE PERMANENTLY LOST! ⚠️"
echo ""

read -p "Are you sure you want to destroy everything? (type 'yes' to confirm): " -r
if [[ ! $REPLY == "yes" ]]; then
    log_info "Destruction cancelled. No resources were deleted."
    exit 0
fi

# Double confirmation for safety
echo ""
log_warning "Last chance to back out!"
read -p "Type 'DELETE' to confirm destruction: " -r
if [[ ! $REPLY == "DELETE" ]]; then
    log_info "Destruction cancelled. No resources were deleted."
    exit 0
fi

# =============================================================================
# 2. Environment Setup
# =============================================================================
log_info "Setting up environment..."

# AWS Configuration
export AWS_REGION="${AWS_REGION:-us-west-2}"
export CDK_DEFAULT_REGION="$AWS_REGION"

# Get AWS Account ID
if ! AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null); then
    log_error "Failed to get AWS Account ID. Please configure AWS credentials."
    exit 1
fi

export CDK_DEFAULT_ACCOUNT="$AWS_ACCOUNT_ID"

log_success "AWS Configuration:"
echo "  Account: $AWS_ACCOUNT_ID"
echo "  Region: $AWS_REGION"
echo ""

# =============================================================================
# 3. Scale Down ECS Services (Speed up deletion)
# =============================================================================
log_info "Scaling down ECS services to 0 tasks..."

scale_down_service() {
    local service_name=$1
    if aws ecs describe-services --cluster ticketing-cluster --services "$service_name" --region "$AWS_REGION" --no-cli-pager &>/dev/null; then
        log_info "Scaling down $service_name to 0 tasks..."
        aws ecs update-service \
            --cluster ticketing-cluster \
            --service "$service_name" \
            --desired-count 0 \
            --region "$AWS_REGION" \
            --no-cli-pager \
            --query 'service.serviceName' \
            --output text || true
        log_success "Scaled down $service_name"
    else
        log_info "Service $service_name not found (may already be deleted)"
    fi
}

scale_down_service "ticketing-service"
scale_down_service "seat-reservation-service"
scale_down_service "kvrocks-master"

log_info "Waiting 30 seconds for tasks to drain..."
sleep 30
echo ""

# =============================================================================
# 4. Destroy CDK Stacks
# =============================================================================
log_info "Destroying CDK stacks..."
log_warning "This will take 10-15 minutes. Please be patient."
echo ""

# Change to deployment/cdk directory where cdk.json is located
SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR/cdk" || exit 1

# Destroy stacks in reverse dependency order
destroy_stack() {
    local stack_name=$1
    log_info "Destroying $stack_name..."

    if aws cloudformation describe-stacks --stack-name "$stack_name" --region "$AWS_REGION" --no-cli-pager &>/dev/null; then
        if uv run cdk destroy "$stack_name" --force --no-cli-pager; then
            log_success "Destroyed $stack_name"
        else
            log_error "Failed to destroy $stack_name (may require manual cleanup)"
        fi
    else
        log_info "$stack_name not found (may already be deleted)"
    fi
    echo ""
}

# Destroy in reverse order of creation
destroy_stack "TicketingLoadTestStack"
destroy_stack "TicketingECSStack"
destroy_stack "TicketingKvrocksStack"
destroy_stack "TicketingMSKStack"
destroy_stack "TicketingAuroraStack"

# Optional: Destroy load balancer stack if it exists
destroy_stack "TicketingLoadBalancerStack"

log_success "All CDK stacks destroyed"
echo ""

# =============================================================================
# 5. Clean Up ECR Images (Optional)
# =============================================================================
log_info "Cleaning up ECR images..."

read -p "Delete ECR images? (yes/no, default: yes): " -r
REPLY=${REPLY:-yes}

if [[ $REPLY =~ ^[Yy](es)?$ ]]; then
    delete_ecr_images() {
        local repo_name=$1
        if aws ecr describe-repositories --repository-names "$repo_name" --region "$AWS_REGION" --no-cli-pager &>/dev/null; then
            log_info "Deleting images from $repo_name..."
            # Get all image IDs
            IMAGE_IDS=$(aws ecr list-images \
                --repository-name "$repo_name" \
                --region "$AWS_REGION" \
                --query 'imageIds[*]' \
                --output json)

            if [[ "$IMAGE_IDS" != "[]" ]]; then
                aws ecr batch-delete-image \
                    --repository-name "$repo_name" \
                    --region "$AWS_REGION" \
                    --image-ids "$IMAGE_IDS" \
                    --no-cli-pager \
                    --query 'imageIds[*].imageDigest' \
                    --output text || true
                log_success "Deleted images from $repo_name"
            else
                log_info "No images found in $repo_name"
            fi
        else
            log_info "ECR repository $repo_name not found"
        fi
    }

    delete_ecr_images "ticketing-service"
    delete_ecr_images "seat-reservation-service"
    echo ""
fi

# =============================================================================
# 6. Delete ECR Repositories (Optional)
# =============================================================================
read -p "Delete ECR repositories? (yes/no, default: no): " -r
REPLY=${REPLY:-no}

if [[ $REPLY =~ ^[Yy](es)?$ ]]; then
    delete_ecr_repo() {
        local repo_name=$1
        if aws ecr describe-repositories --repository-names "$repo_name" --region "$AWS_REGION" --no-cli-pager &>/dev/null; then
            log_info "Deleting ECR repository: $repo_name..."
            aws ecr delete-repository \
                --repository-name "$repo_name" \
                --region "$AWS_REGION" \
                --force \
                --no-cli-pager
            log_success "Deleted ECR repository: $repo_name"
        fi
    }

    delete_ecr_repo "ticketing-service"
    delete_ecr_repo "seat-reservation-service"
    echo ""
fi

# =============================================================================
# 7. Clean Up CloudWatch Logs (Optional)
# =============================================================================
read -p "Delete CloudWatch Logs? (yes/no, default: no): " -r
REPLY=${REPLY:-no}

if [[ $REPLY =~ ^[Yy](es)?$ ]]; then
    log_info "Deleting CloudWatch log groups..."

    delete_log_group() {
        local log_group=$1
        if aws logs describe-log-groups --log-group-name-prefix "$log_group" --region "$AWS_REGION" --no-cli-pager &>/dev/null; then
            log_info "Deleting log group: $log_group..."
            aws logs delete-log-group \
                --log-group-name "$log_group" \
                --region "$AWS_REGION" \
                --no-cli-pager || true
            log_success "Deleted log group: $log_group"
        fi
    }

    # Delete all ECS-related log groups
    delete_log_group "/aws/ecs/ticketing"
    delete_log_group "/aws/ecs/reservation"
    delete_log_group "/aws/ecs/adot-collector"
    delete_log_group "/aws/ecs/adot-collector-reservation"
    delete_log_group "/aws/ecs/kvrocks-master"
    echo ""
fi

# =============================================================================
# 8. Verify Cleanup
# =============================================================================
log_info "Verifying cleanup..."

# Check if any stacks remain
REMAINING_STACKS=$(aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --region "$AWS_REGION" \
    --query 'StackSummaries[?starts_with(StackName, `Ticketing`)].StackName' \
    --output text)

if [[ -z "$REMAINING_STACKS" ]]; then
    log_success "All Ticketing stacks have been deleted"
else
    log_warning "Some stacks may still exist:"
    echo "$REMAINING_STACKS"
    echo ""
    log_info "You may need to manually delete these stacks from the CloudFormation console"
fi

# Check for running ECS tasks
RUNNING_TASKS=$(aws ecs list-tasks \
    --cluster ticketing-cluster \
    --region "$AWS_REGION" \
    --query 'taskArns' \
    --output text 2>/dev/null || echo "")

if [[ -z "$RUNNING_TASKS" ]]; then
    log_success "No ECS tasks are running"
else
    log_warning "Some ECS tasks may still be running (they will stop soon)"
fi

echo ""

# =============================================================================
# 9. Cleanup Summary
# =============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                   🎉 CLEANUP COMPLETED                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

log_success "Deleted Resources:"
echo "  🗑️  Aurora Serverless v2"
echo "  🗑️  Amazon MSK"
echo "  🗑️  Kvrocks ECS Service"
echo "  🗑️  Ticketing & Seat Reservation Services"
echo "  🗑️  Application Load Balancer"
echo "  🗑️  VPC & Security Groups"
echo ""

log_success "Cost Savings:"
echo "  💰 Stopped paying ~\$3-5 per hour"
echo "  💰 Stopped paying ~\$72-120 per day"
echo ""

log_info "What's Left:"
echo "  ✅ CDK Bootstrap stack (CDKToolkit) - keeps S3/IAM for next deployment"
echo "  ✅ ECR repositories (if you chose to keep them)"
echo "  ✅ CloudWatch logs (if you chose to keep them)"
echo ""

log_warning "To completely remove CDK:"
echo "  aws cloudformation delete-stack --stack-name CDKToolkit --region $AWS_REGION"
echo ""

log_info "To redeploy tomorrow:"
echo "  ./deployment/deploy-all.sh"
echo ""

# Clean up deployment info file
if [[ -f deployment/last-deployment.txt ]]; then
    mv deployment/last-deployment.txt deployment/last-deployment-deleted-$(date +%Y%m%d-%H%M%S).txt
    log_info "Deployment info archived"
fi

log_success "All done! 👋"
echo ""
