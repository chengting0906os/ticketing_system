#!/bin/bash
# =============================================================================
# ECR Push Script - Build and push Docker images to AWS ECR
# =============================================================================
# Usage:
#   ./ecr-push.sh <environment> [service]
#
# Arguments:
#   environment: production | development
#   service: ticketing | reservation | all (default: all)
#
# Examples:
#   ./ecr-push.sh production all           # Push all services
#   ./ecr-push.sh development ticketing    # Push only ticketing service
#   ./ecr-push.sh production reservation   # Push only reservation service
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker installed and running
#   - IAM permissions for ECR
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

ENVIRONMENT="${1:-}"
SERVICE="${2:-all}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# AWS Configuration
AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"

# Service Configuration (list of repository names)
REPOSITORIES=(
    "ticketing-service"
    "reservation-service"
)

# Docker Configuration
DOCKERFILE="Dockerfile"
BUILD_TARGET="production"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

print_usage() {
    echo "Usage: $0 <environment> [service]"
    echo ""
    echo "Arguments:"
    echo "  environment: production | development"
    echo "  service: ticketing | reservation | all (default: all)"
    echo ""
    echo "Examples:"
    echo "  $0 production all"
    echo "  $0 development ticketing"
    echo "  $0 production reservation"
    exit 1
}

# =============================================================================
# Validation
# =============================================================================

if [ -z "$ENVIRONMENT" ]; then
    log_error "Environment argument is required"
    print_usage
fi

if [[ ! "$ENVIRONMENT" =~ ^(production|development)$ ]]; then
    log_error "Invalid environment: $ENVIRONMENT"
    print_usage
fi

if [[ ! "$SERVICE" =~ ^(ticketing|reservation|all)$ ]]; then
    log_error "Invalid service: $SERVICE"
    print_usage
fi

# Check dependencies
for cmd in aws docker git; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd is not installed"
        exit 1
    fi
done

if ! docker info &> /dev/null; then
    log_error "Docker daemon is not running"
    exit 1
fi

# =============================================================================
# AWS Setup
# =============================================================================

log_info "Detecting AWS account information..."

if [ -z "$AWS_ACCOUNT_ID" ]; then
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        log_error "Failed to detect AWS account ID. Run 'aws configure' first"
        exit 1
    fi
fi

log_success "AWS Account: $AWS_ACCOUNT_ID"
log_success "Region: $AWS_REGION"
log_success "Environment: $ENVIRONMENT"
log_success "Service: $SERVICE"

# ECR Authentication
log_info "Authenticating with ECR..."
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY" &>/dev/null; then
    log_success "ECR authentication successful"
else
    log_error "ECR authentication failed"
    exit 1
fi

# =============================================================================
# Core Build & Push Function
# =============================================================================

build_and_push() {
    local repo_name=$1
    local service_name=$2
    local dockerfile="${3:-$DOCKERFILE}"
    local build_context="${4:-.}"

    log_info "================================================"
    log_info "Building: $service_name"
    log_info "================================================"

    local image_uri="${ECR_REGISTRY}/${repo_name}"
    local commit_sha=$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')
    local image_tag="${ENVIRONMENT}-${commit_sha}"

    log_info "Repository: $repo_name"
    log_info "Image URI: $image_uri"
    log_info "Tags: $image_tag, ${ENVIRONMENT}-latest, latest"

    # Ensure ECR repository exists
    if ! aws ecr describe-repositories --repository-names "$repo_name" --region "$AWS_REGION" &>/dev/null; then
        log_warning "Creating repository: $repo_name"
        aws ecr create-repository \
            --repository-name "$repo_name" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256 \
            >/dev/null
        log_success "Repository created"
    fi

    # Build image
    log_info "Building Docker image..."
    # Only use --target for Python services (main Dockerfile)
    # Go loadtest Dockerfile doesn't have named production stage
    local build_args="--platform linux/amd64 \
        --tag ${image_uri}:${image_tag} \
        --tag ${image_uri}:${ENVIRONMENT}-latest \
        --tag ${image_uri}:latest \
        --build-arg SERVICE_NAME=$service_name \
        --build-arg ENVIRONMENT=$ENVIRONMENT \
        --file $dockerfile \
        $build_context"

    if [ "$dockerfile" = "$DOCKERFILE" ]; then
        # Python services: use production stage
        build_args="--target $BUILD_TARGET $build_args"
    fi

    if ! docker build $build_args 2>&1 | grep -E "^(#|=>|ERROR)" ; then
        log_error "Build failed for $service_name"
        return 1
    fi
    log_success "Build completed"

    # Push all tags
    for tag in "$image_tag" "${ENVIRONMENT}-latest" "latest"; do
        log_info "Pushing tag: $tag"
        if docker push "${image_uri}:${tag}" >/dev/null 2>&1; then
            log_success "Pushed: $tag"
        else
            log_error "Failed to push: $tag"
            return 1
        fi
    done

    log_success "✅ Successfully pushed $service_name"
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================

log_info "================================================"
log_info "Starting ECR Push Process"
log_info "================================================"
echo ""

cd "$(dirname "$0")/../.."

# Build and push services
case "$SERVICE" in
    all)
        build_and_push "ticketing-service" "ticketing-service"
        build_and_push "reservation-service" "reservation-service"
        ;;
    ticketing)
        build_and_push "ticketing-service" "ticketing-service"
        ;;
    reservation)
        build_and_push "reservation-service" "reservation-service"
        ;;
esac

# =============================================================================
# Summary
# =============================================================================

log_success "================================================"
log_success "ECR Push Completed"
log_success "================================================"
log_info "Next steps:"
log_info "  • Deploy CDK stacks: cdk deploy --all"
log_info "  • Monitor CloudWatch Logs"
log_info "  • Check ECS service health"
echo ""
log_info "View images:"
for repo in "${REPOSITORIES[@]}"; do
    log_info "  aws ecr list-images --repository-name $repo --region $AWS_REGION"
done
