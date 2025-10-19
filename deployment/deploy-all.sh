#!/bin/bash
# =============================================================================
# AWS One-Click Deployment Script
# =============================================================================
# Purpose: Deploy complete Ticketing System to AWS (10000 TPS Architecture)
# Usage: make deploy  or  ./deployment/deploy-all.sh
# Time: ~30 minutes
# Cost: ~$3-5/hour
# =============================================================================

set -euo pipefail  # Exit on error, undefined var, pipe failure

# ============= Constants =============
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ============= Colors =============
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# ============= Logging Functions =============
log_info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error()   { echo -e "${RED}❌ $*${NC}" >&2; }
log_step()    { echo ""; echo "━━━ $* ━━━"; }

# ============= Setup Environment =============
setup_environment() {
    log_step "1/10 Environment Setup"

    export AWS_REGION="${AWS_REGION:-us-west-2}"
    export CDK_DEFAULT_REGION="$AWS_REGION"
    export DEPLOY_ENV="${DEPLOY_ENV:-development}"

    if ! AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null); then
        log_error "AWS credentials not configured"
        echo "Run: aws configure"
        exit 1
    fi

    export CDK_DEFAULT_ACCOUNT="$AWS_ACCOUNT_ID"

    log_success "Environment ready"
    echo "  Account: $AWS_ACCOUNT_ID"
    echo "  Region: $AWS_REGION"
    echo "  Config: $DEPLOY_ENV"
}

# ============= Confirm Deployment =============
confirm_deployment() {
    log_warning "⚠️  AWS resources will incur costs (~\$3-5/hour)"
    read -p "Continue? (yes/no): " -r
    [[ $REPLY =~ ^[Yy](es)?$ ]] || { log_info "Cancelled"; exit 0; }
}

# ============= Bootstrap CDK =============
bootstrap_cdk() {
    log_step "2/10 CDK Bootstrap"

    if aws cloudformation describe-stacks --stack-name CDKToolkit --region "$AWS_REGION" &>/dev/null; then
        log_success "Already bootstrapped"
    else
        log_info "Bootstrapping (first-time setup)..."
        cd "$SCRIPT_DIR/cdk" && uv run cdk bootstrap "aws://$AWS_ACCOUNT_ID/$AWS_REGION"
        log_success "Bootstrap completed"
    fi
}

# ============= Create ECR Repositories =============
create_ecr_repositories() {
    log_step "3/10 ECR Repositories"

    local repos=("ticketing-service" "seat-reservation-service")

    for repo in "${repos[@]}"; do
        log_info "Checking $repo..."
        if aws ecr describe-repositories \
            --repository-names "$repo" \
            --region "$AWS_REGION" \
            --no-cli-pager &>/dev/null; then
            log_success "$repo (exists)"
        else
            log_info "Creating $repo..."
            aws ecr create-repository \
                --repository-name "$repo" \
                --region "$AWS_REGION" \
                --image-scanning-configuration scanOnPush=true \
                --no-cli-pager >/dev/null || {
                log_error "Failed to create $repo"
                exit 1
            }
            log_success "$repo (created)"
        fi
    done
}

# ============= Validate CDK Configuration =============
validate_cdk() {
    log_step "4/10 Validate Configuration"

    cd "$SCRIPT_DIR/cdk"
    uv run cdk synth --all --quiet || {
        log_error "CDK synthesis failed"
        exit 1
    }
    log_success "Configuration valid"
}

# ============= Deploy Infrastructure =============
deploy_infrastructure() {
    log_step "5/10 Deploy Infrastructure (20-30 min ☕)"

    cd "$SCRIPT_DIR/cdk"
    uv run cdk deploy \
        TicketingAuroraStack \
        TicketingMSKStack \
        TicketingKvrocksStack \
        TicketingECSStack \
        --require-approval never \
        --outputs-file cdk-outputs.json \
        --no-cli-pager

    log_success "Infrastructure deployed"
}

# ============= Build and Push Docker Images =============
build_and_push_images() {
    log_step "6/10 Build Docker Images"

    cd "$PROJECT_ROOT"

    # Login to ECR
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin \
        "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com" >/dev/null

    local services=("ticketing-service" "seat-reservation-service")

    for service in "${services[@]}"; do
        log_info "Building $service..."
        docker build \
            --target production \
            --platform linux/amd64 \
            -t "$service:latest" \
            -f Dockerfile . \
            --quiet

        docker tag "$service:latest" \
            "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$service:latest"

        docker push \
            "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$service:latest" | \
            grep -E "digest:|Pushed" || true

        log_success "$service pushed"
    done
}

# ============= Update ECS Services =============
update_ecs_services() {
    log_step "7/10 Update ECS Services"

    local services=("ticketing-service" "seat-reservation-service")

    for service in "${services[@]}"; do
        aws ecs update-service \
            --cluster ticketing-cluster \
            --service "$service" \
            --force-new-deployment \
            --region "$AWS_REGION" \
            --no-cli-pager \
            --query 'service.serviceName' \
            --output text >/dev/null
        log_success "$service restarting"
    done
}

# ============= Wait for Services =============
wait_for_services() {
    log_step "8/10 Wait for Services (5-10 min)"

    aws ecs wait services-stable \
        --cluster ticketing-cluster \
        --services ticketing-service seat-reservation-service \
        --region "$AWS_REGION"

    log_success "Services stable"
}

# ============= Health Check =============
health_check() {
    log_step "9/10 Health Check"

    local alb_endpoint
    alb_endpoint=$(jq -r '.TicketingECSStack.ALBEndpoint' "$SCRIPT_DIR/cdk/cdk-outputs.json")

    [[ -z "$alb_endpoint" || "$alb_endpoint" == "null" ]] && {
        log_error "ALB endpoint not found"
        exit 1
    }

    local max_attempts=10
    for attempt in $(seq 1 $max_attempts); do
        if curl -f -s "$alb_endpoint/health" >/dev/null 2>&1; then
            log_success "Health check passed"
            echo "$alb_endpoint"
            return 0
        fi
        log_info "Attempt $attempt/$max_attempts... (retry in 30s)"
        sleep 30
    done

    log_warning "Health check timeout (services may still be starting)"
    echo "$alb_endpoint"
}

# ============= Print Summary =============
print_summary() {
    local alb_endpoint=$1

    log_step "10/10 Deployment Complete 🎉"

    cat <<EOF

╔══════════════════════════════════════════════════════════╗
║                  DEPLOYMENT SUCCESSFUL                   ║
╚══════════════════════════════════════════════════════════╝

📍 Region: $AWS_REGION
🏢 Account: $AWS_ACCOUNT_ID
🌐 Endpoint: $alb_endpoint

🔗 APIs:
   Health:      $alb_endpoint/health
   Ticketing:   $alb_endpoint/api/user/*
   Reservation: $alb_endpoint/api/reservation/*

📊 Monitoring:
   make monitor                               # Real-time
   https://console.aws.amazon.com/xray        # X-Ray
   https://console.aws.amazon.com/ecs         # ECS Console

💰 Cost: ~\$3-5/hour (~\$72-120/day)
🛑 Shutdown: make destroy

📝 Next Steps:
   1. make k6-load     # Load test
   2. make monitor     # Watch metrics
   3. make destroy     # Clean up

EOF

    # Save deployment info
    cat > "$SCRIPT_DIR/last-deployment.txt" <<EOF
Deployment Time: $(date)
Region: $AWS_REGION
Account: $AWS_ACCOUNT_ID
ALB Endpoint: $alb_endpoint
EOF
}

# ============= Main Execution =============
main() {
    setup_environment
    confirm_deployment
    bootstrap_cdk
    create_ecr_repositories
    validate_cdk
    deploy_infrastructure
    build_and_push_images
    update_ecs_services
    wait_for_services
    local alb_endpoint
    alb_endpoint=$(health_check)
    print_summary "$alb_endpoint"
}

main "$@"
