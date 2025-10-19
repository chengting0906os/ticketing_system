#!/bin/bash
# =============================================================================
# AWS Start-All Script (Resume Services)
# =============================================================================
# Purpose: Resume all ECS services after stop-all.sh
# Usage: make start  or  ./deployment/start-all.sh
# Time: ~5-8 minutes (wait for services to become healthy)
# Cost: Resume to ~$3-5/hour
# =============================================================================

set -euo pipefail  # Exit on error, undefined var, pipe failure

# ============= Constants =============
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly AWS_REGION="${AWS_REGION:-us-west-2}"

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

# ============= Check AWS Credentials =============
check_aws() {
    log_step "1/5 Checking AWS Credentials"

    if ! aws sts get-caller-identity --query Account --output text &>/dev/null; then
        log_error "AWS credentials not configured"
        echo "Run: aws configure"
        exit 1
    fi

    log_success "AWS credentials valid"
}

# ============= Start Kvrocks Service =============
start_kvrocks_service() {
    log_step "2/5 Starting Kvrocks Service"

    local cluster="ticketing-shared-cluster"
    local service="kvrocks-master"

    log_info "Starting $service (1 task)..."

    if aws ecs update-service \
        --cluster "$cluster" \
        --service "$service" \
        --desired-count 1 \
        --region "$AWS_REGION" \
        --no-cli-pager \
        --query 'service.serviceName' \
        --output text &>/dev/null; then
        log_success "$service → 1 task"
    else
        log_error "Failed to start $service"
        exit 1
    fi

    # Wait for Kvrocks to be healthy
    log_info "Waiting for Kvrocks to be healthy (60s)..."
    sleep 60
}

# ============= Start ECS Services =============
start_ecs_services() {
    log_step "3/5 Starting ECS Services"

    local cluster="ticketing-cluster"
    local services=("ticketing-service" "seat-reservation-service")
    local desired_count=4  # Minimum auto-scaling count

    for service in "${services[@]}"; do
        log_info "Starting $service ($desired_count tasks)..."

        if aws ecs update-service \
            --cluster "$cluster" \
            --service "$service" \
            --desired-count "$desired_count" \
            --region "$AWS_REGION" \
            --no-cli-pager \
            --query 'service.serviceName' \
            --output text &>/dev/null; then
            log_success "$service → $desired_count tasks"
        else
            log_error "Failed to start $service"
            exit 1
        fi
    done
}

# ============= Wait for Services =============
wait_for_services() {
    log_step "4/5 Waiting for Services (5-8 min ☕)"

    local cluster="ticketing-cluster"
    local services=("ticketing-service" "seat-reservation-service")

    log_info "Waiting for services to stabilize..."

    if aws ecs wait services-stable \
        --cluster "$cluster" \
        --services "${services[@]}" \
        --region "$AWS_REGION"; then
        log_success "All services stable"
    else
        log_warning "Timeout waiting for services (check AWS Console)"
    fi
}

# ============= Health Check =============
health_check() {
    log_step "5/5 Health Check"

    local alb_endpoint
    if [[ -f "$SCRIPT_DIR/cdk/cdk-outputs.json" ]]; then
        alb_endpoint=$(jq -r '.TicketingECSStack.ALBEndpoint' "$SCRIPT_DIR/cdk/cdk-outputs.json" 2>/dev/null || echo "")
    fi

    if [[ -z "$alb_endpoint" || "$alb_endpoint" == "null" ]]; then
        log_warning "ALB endpoint not found in cdk-outputs.json"
        log_info "Get endpoint from AWS Console: https://console.aws.amazon.com/ec2/v2/home?region=$AWS_REGION#LoadBalancers"
        return 0
    fi

    log_info "Testing endpoint: $alb_endpoint"

    local max_attempts=10
    for attempt in $(seq 1 $max_attempts); do
        if curl -f -s "$alb_endpoint/health" >/dev/null 2>&1; then
            log_success "Health check passed!"
            echo "  URL: $alb_endpoint/health"
            return 0
        fi
        log_info "Attempt $attempt/$max_attempts... (retry in 30s)"
        sleep 30
    done

    log_warning "Health check timeout (services may still be initializing)"
    echo "  URL: $alb_endpoint/health"
}

# ============= Print Summary =============
print_summary() {
    log_step "Services Started 🚀"

    cat <<EOF

╔══════════════════════════════════════════════════════════╗
║              SERVICES STARTED SUCCESSFULLY               ║
╚══════════════════════════════════════════════════════════╝

🚀 Running Services:
   • ticketing-service (4 tasks, auto-scales to 16)
   • seat-reservation-service (4 tasks, auto-scales to 16)
   • kvrocks-master (1 task)

💰 Current Cost: ~\$3-5/hour

📊 Monitoring:
   make monitor                               # Real-time
   https://console.aws.amazon.com/ecs         # ECS Console
   https://console.aws.amazon.com/xray        # X-Ray Tracing

🛑 Stop Services (save costs):
   ./deployment/stop-all.sh

🗑️  Complete Cleanup:
   make destroy  # Delete all resources

EOF

    # Save start timestamp
    cat > "$SCRIPT_DIR/last-start.txt" <<EOF
Start Time: $(date)
Region: $AWS_REGION
Status: All services running (4 tasks minimum)
EOF
}

# ============= Main Execution =============
main() {
    check_aws
    start_kvrocks_service
    start_ecs_services
    wait_for_services
    health_check
    print_summary
}

main "$@"
