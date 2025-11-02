#!/bin/bash
# =============================================================================
# ECR Push Script - Build and push Docker images to AWS ECR
# =============================================================================
# Usage:
#   ./ecr-push.sh <environment> [service]
#
# Arguments:
#   environment: production | development
#   service: api | ticketing-consumer | reservation-consumer | all (default: all)
#
# Examples:
#   ./ecr-push.sh production all                     # Push all services
#   ./ecr-push.sh development api                    # Push only API service
#   ./ecr-push.sh production ticketing-consumer      # Push only ticketing consumer
#   ./ecr-push.sh production reservation-consumer    # Push only reservation consumer
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker installed and running
#   - IAM permissions for ECR (ecr:GetAuthorizationToken, ecr:PutImage, etc.)
# =============================================================================

set -euo pipefail  # Exit on error, undefined variables, and pipe failures

# =============================================================================
# Configuration
# =============================================================================

ENVIRONMENT="${1:-}"
SERVICE="${2:-all}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# AWS Configuration (will be auto-detected or set via environment variables)
AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"

# ECR Repository names (must match CDK stack names)
TICKETING_REPO="ticketing-service"
TICKETING_CONSUMER_REPO="ticketing-consumer"
RESERVATION_CONSUMER_REPO="seat-reservation-consumer"

# Docker build configuration
DOCKERFILE="Dockerfile"
BUILD_TARGET="production"  # Use production stage from multi-stage Dockerfile

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_usage() {
    echo "Usage: $0 <environment> [service]"
    echo ""
    echo "Arguments:"
    echo "  environment: production | development"
    echo "  service: api | ticketing-consumer | reservation-consumer | all (default: all)"
    echo ""
    echo "Examples:"
    echo "  $0 production all"
    echo "  $0 development api"
    echo "  $0 production ticketing-consumer"
    exit 1
}

# =============================================================================
# Validation
# =============================================================================

# Check arguments
if [ -z "$ENVIRONMENT" ]; then
    log_error "Environment argument is required"
    print_usage
fi

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(production|development)$ ]]; then
    log_error "Invalid environment: $ENVIRONMENT"
    print_usage
fi

# Validate service
if [[ ! "$SERVICE" =~ ^(api|ticketing-consumer|reservation-consumer|all)$ ]]; then
    log_error "Invalid service: $SERVICE"
    print_usage
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed. Install it from: https://aws.amazon.com/cli/"
    exit 1
fi

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed"
    exit 1
fi

if ! docker info &> /dev/null; then
    log_error "Docker daemon is not running"
    exit 1
fi

# =============================================================================
# AWS Account Detection
# =============================================================================

log_info "Detecting AWS account information..."

# Get AWS account ID if not set
if [ -z "$AWS_ACCOUNT_ID" ]; then
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)

    if [ -z "$AWS_ACCOUNT_ID" ]; then
        log_error "Failed to detect AWS account ID. Please run 'aws configure' first"
        exit 1
    fi
fi

log_success "AWS Account ID: $AWS_ACCOUNT_ID"
log_success "AWS Region: $AWS_REGION"
log_success "Environment: $ENVIRONMENT"
log_success "Service: $SERVICE"

# =============================================================================
# ECR Authentication
# =============================================================================

log_info "Authenticating with ECR..."

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Get ECR login password and authenticate Docker
if aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY" 2>/dev/null; then
    log_success "ECR authentication successful"
else
    log_error "ECR authentication failed. Check your AWS credentials and IAM permissions"
    exit 1
fi

# =============================================================================
# Build and Push Function
# =============================================================================

build_and_push() {
    local service_name=$1
    local repo_name=$2

    log_info "================================================"
    log_info "Building and pushing: $service_name"
    log_info "================================================"

    # Full ECR image URI
    local image_uri="${ECR_REGISTRY}/${repo_name}"
    local image_tag="${ENVIRONMENT}-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')"
    local full_image_uri="${image_uri}:${image_tag}"
    local env_latest_uri="${image_uri}:${ENVIRONMENT}-latest"
    local latest_image_uri="${image_uri}:latest"  # Universal latest tag for ECS

    log_info "Image URI: $full_image_uri"

    # Create ECR repository if it doesn't exist
    log_info "Checking if ECR repository exists..."
    if ! aws ecr describe-repositories --repository-names "$repo_name" --region "$AWS_REGION" &>/dev/null; then
        log_warning "Repository $repo_name does not exist. Creating..."
        aws ecr create-repository \
            --repository-name "$repo_name" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256 \
            >/dev/null
        log_success "Repository created: $repo_name"
    else
        log_success "Repository exists: $repo_name"
    fi

    # Build Docker image
    log_info "Building Docker image..."
    if docker build \
        --target "$BUILD_TARGET" \
        --platform linux/amd64 \
        --tag "$full_image_uri" \
        --tag "$env_latest_uri" \
        --tag "$latest_image_uri" \
        --build-arg SERVICE_NAME="$service_name" \
        --build-arg ENVIRONMENT="$ENVIRONMENT" \
        --file "$DOCKERFILE" \
        . ; then
        log_success "Docker build completed"
    else
        log_error "Docker build failed for $service_name"
        return 1
    fi

    # Push Docker image with commit SHA tag
    log_info "Pushing image with tag: $image_tag"
    if docker push "$full_image_uri"; then
        log_success "Pushed: $full_image_uri"
    else
        log_error "Failed to push: $full_image_uri"
        return 1
    fi

    # Push Docker image with environment-specific latest tag
    log_info "Pushing image with tag: ${ENVIRONMENT}-latest"
    if docker push "$env_latest_uri"; then
        log_success "Pushed: $env_latest_uri"
    else
        log_error "Failed to push: $env_latest_uri"
        return 1
    fi

    # Push Docker image with universal latest tag (for ECS)
    log_info "Pushing image with tag: latest"
    if docker push "$latest_image_uri"; then
        log_success "Pushed: $latest_image_uri"
    else
        log_error "Failed to push: $latest_image_uri"
        return 1
    fi

    log_success "✅ Successfully pushed $service_name to ECR"
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================

log_info "================================================"
log_info "Starting ECR Push Process"
log_info "================================================"
echo ""

# Navigate to project root (assumes script is in deployment/scripts/)
cd "$(dirname "$0")/../.."

# Build and push based on service selection
if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "api" ]; then
    build_and_push "ticketing-service" "$TICKETING_REPO"
fi

if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "ticketing-consumer" ]; then
    build_and_push "ticketing-consumer" "$TICKETING_CONSUMER_REPO"
fi

if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "reservation-consumer" ]; then
    build_and_push "seat-reservation-consumer" "$RESERVATION_CONSUMER_REPO"
fi

# =============================================================================
# Summary
# =============================================================================

log_success "================================================"
log_success "ECR Push Process Completed"
log_success "================================================"
log_info "Next steps:"
log_info "  1. Update ECS service to use new image tags"
log_info "  2. Monitor CloudWatch Logs for deployment status"
log_info "  3. Check ALB target health in AWS Console"
echo ""
log_info "View images in ECR:"
log_info "  aws ecr list-images --repository-name $TICKETING_REPO --region $AWS_REGION"
log_info "  aws ecr list-images --repository-name $TICKETING_CONSUMER_REPO --region $AWS_REGION"
log_info "  aws ecr list-images --repository-name $RESERVATION_CONSUMER_REPO --region $AWS_REGION"
