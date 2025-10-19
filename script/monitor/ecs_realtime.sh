#!/bin/bash
# Real-time ECS monitoring script for load testing
# Usage: ./monitor_ecs_realtime.sh [cluster-name] [service-name]

set -euo pipefail

# Configuration
CLUSTER_NAME="${1:-ticketing-cluster}"
SERVICE_NAME="${2:-ticketing-service}"
REGION="${AWS_REGION:-us-west-2}"
REFRESH_INTERVAL=5  # seconds

echo "🔍 Monitoring ECS Service: $SERVICE_NAME in cluster $CLUSTER_NAME"
echo "📍 Region: $REGION"
echo "🔄 Refresh interval: ${REFRESH_INTERVAL}s"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# TODO(human): Implement the monitoring loop
#
# The loop should:
# 1. Get current task count using aws ecs describe-services
# 2. Get CPU utilization from CloudWatch (last 1 minute average)
# 3. Get Memory utilization from CloudWatch (last 1 minute average)
# 4. Display results in a clear format
#
# Hints:
# - Use `aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME`
# - Use `aws cloudwatch get-metric-statistics` with namespace AWS/ECS
# - Handle cases where metrics are not yet available
# - Use --start-time and --end-time for recent data
# - Consider using `date -u -v-1M` (macOS) or `date -u -d '1 minute ago'` (Linux)

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Get service info (immediate, no delay)
    SERVICE_INFO=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$REGION" \
        --query 'services[0]' \
        --output json 2>/dev/null)

    if [ -z "$SERVICE_INFO" ] || [ "$SERVICE_INFO" = "null" ]; then
        echo "[$TIMESTAMP] ❌ Service not found: $SERVICE_NAME"
        sleep $REFRESH_INTERVAL
        continue
    fi

    RUNNING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.runningCount // 0')
    DESIRED_COUNT=$(echo "$SERVICE_INFO" | jq -r '.desiredCount // 0')
    PENDING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.pendingCount // 0')

    # Get CloudWatch metrics (2 minute window to account for delay)
    START_TIME=$(date -u -v-2M '+%Y-%m-%dT%H:%M:%S' 2>/dev/null || date -u -d '2 minutes ago' '+%Y-%m-%dT%H:%M:%S')
    END_TIME=$(date -u '+%Y-%m-%dT%H:%M:%S')

    # Query CPU utilization
    CPU_DATA=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ECS \
        --metric-name CPUUtilization \
        --dimensions Name=ServiceName,Value="$SERVICE_NAME" Name=ClusterName,Value="$CLUSTER_NAME" \
        --start-time "$START_TIME" \
        --end-time "$END_TIME" \
        --period 60 \
        --statistics Average \
        --region "$REGION" \
        --output json 2>/dev/null)

    CPU_USAGE=$(echo "$CPU_DATA" | jq -r '.Datapoints | if length > 0 then (.[0].Average | floor) else "N/A" end')

    # Query Memory utilization
    MEM_DATA=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ECS \
        --metric-name MemoryUtilization \
        --dimensions Name=ServiceName,Value="$SERVICE_NAME" Name=ClusterName,Value="$CLUSTER_NAME" \
        --start-time "$START_TIME" \
        --end-time "$END_TIME" \
        --period 60 \
        --statistics Average \
        --region "$REGION" \
        --output json 2>/dev/null)

    MEMORY_USAGE=$(echo "$MEM_DATA" | jq -r '.Datapoints | if length > 0 then (.[0].Average | floor) else "N/A" end')

    # Display results with color coding
    TASK_INFO="Tasks: $RUNNING_COUNT/$DESIRED_COUNT"
    [ "$PENDING_COUNT" -gt 0 ] && TASK_INFO="$TASK_INFO (⏳ $PENDING_COUNT pending)"

    CPU_INFO="CPU: ${CPU_USAGE}%"
    [ "$CPU_USAGE" != "N/A" ] && [ "$CPU_USAGE" -gt 80 ] && CPU_INFO="$CPU_INFO ⚠️"

    MEM_INFO="Mem: ${MEMORY_USAGE}%"
    [ "$MEMORY_USAGE" != "N/A" ] && [ "$MEMORY_USAGE" -gt 85 ] && MEM_INFO="$MEM_INFO ⚠️"

    echo "[$TIMESTAMP] $TASK_INFO | $CPU_INFO | $MEM_INFO"

    sleep $REFRESH_INTERVAL
done
