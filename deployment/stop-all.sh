#!/bin/bash
# =============================================================================
# AWS Stop-All Script (Cost Saving)
# =============================================================================
# Purpose: Stop all ECS services to save costs (keep infrastructure)
# Usage: make stop  or  ./deployment/stop-all.sh
# Time: ~2 minutes
# Savings: ~$2-4/hour (only pay for Aurora, MSK, EFS storage)
# Resume: ./deployment/start-all.sh
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
    log_step "1/4 Checking AWS Credentials"

    if ! aws sts get-caller-identity --query Account --output text &>/dev/null; then
        log_error "AWS credentials not configured"
        echo "Run: aws configure"
        exit 1
    fi

    log_success "AWS credentials valid"
}

# ============= Stop ECS Services =============
stop_ecs_services() {
    log_step "2/4 Stopping ECS Services"

    local cluster="ticketing-cluster"
    local services=("ticketing-service" "seat-reservation-service")

    # Check if cluster exists
    if ! aws ecs describe-clusters \
        --clusters "$cluster" \
        --region "$AWS_REGION" \
        --query 'clusters[0].status' \
        --output text 2>/dev/null | grep -q "ACTIVE"; then
        log_warning "Cluster '$cluster' not found or inactive"
        return 0
    fi

    for service in "${services[@]}"; do
        log_info "Stopping $service..."

        # Scale down to 0 tasks
        if aws ecs update-service \
            --cluster "$cluster" \
            --service "$service" \
            --desired-count 0 \
            --region "$AWS_REGION" \
            --no-cli-pager \
            --query 'service.serviceName' \
            --output text &>/dev/null; then
            log_success "$service → 0 tasks"
        else
            log_warning "$service not found or already stopped"
        fi
    done
}

# ============= Stop Kvrocks Service =============
stop_kvrocks_service() {
    log_step "3/4 Stopping Kvrocks Service"

    local cluster="ticketing-shared-cluster"
    local service="kvrocks-master"

    # Check if cluster exists
    if ! aws ecs describe-clusters \
        --clusters "$cluster" \
        --region "$AWS_REGION" \
        --query 'clusters[0].status' \
        --output text 2>/dev/null | grep -q "ACTIVE"; then
        log_warning "Cluster '$cluster' not found or inactive"
        return 0
    fi

    log_info "Stopping $service..."

    if aws ecs update-service \
        --cluster "$cluster" \
        --service "$service" \
        --desired-count 0 \
        --region "$AWS_REGION" \
        --no-cli-pager \
        --query 'service.serviceName' \
        --output text &>/dev/null; then
        log_success "$service → 0 tasks"
    else
        log_warning "$service not found or already stopped"
    fi
}

# ============= Print Summary =============
print_summary() {
    log_step "4/4 Services Stopped 🛑"

    cat <<EOF

╔══════════════════════════════════════════════════════════╗
║               SERVICES STOPPED SUCCESSFULLY              ║
╚══════════════════════════════════════════════════════════╝

🛑 Stopped Services:
   • ticketing-service
   • seat-reservation-service
   • kvrocks-master

💰 Cost Savings: ~\$2-4/hour
   Still running (minimal cost):
   • Aurora Serverless v2 (pauses after 5 min idle)
   • MSK (3-broker Kafka cluster)
   • EFS storage (pay per GB)
   • VPC and networking (free)

📊 Current Cost: ~\$0.50-1/hour (storage + networking)

🚀 Resume Services:
   ./deployment/start-all.sh
   (or manually update ECS service desired count)

🗑️  Complete Cleanup:
   make destroy  # Delete all resources

⚠️  Note: Aurora may take 5-10 minutes to pause automatically

EOF

    # Save stop timestamp
    cat > "$SCRIPT_DIR/last-stop.txt" <<EOF
Stop Time: $(date)
Region: $AWS_REGION
Status: All ECS services scaled to 0
EOF
}

# ============= Main Execution =============
main() {
    check_aws
    stop_ecs_services
    stop_kvrocks_service
    print_summary
}

main "$@"
