#!/bin/bash
# Monitor all services in the ticketing cluster
# Usage: ./monitor_all_services.sh [cluster-name]

set -euo pipefail

CLUSTER_NAME="${1:-ticketing-cluster}"
REGION="${AWS_REGION:-us-west-2}"
REFRESH_INTERVAL=5

echo "🔍 Monitoring ECS Cluster: $CLUSTER_NAME"
echo "📍 Region: $REGION"
echo "🔄 Refresh interval: ${REFRESH_INTERVAL}s"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

SERVICES=("ticketing-service" "seat-reservation-service" "kvrocks-master")

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP]"

    for SERVICE_NAME in "${SERVICES[@]}"; do
        # Get service info
        SERVICE_INFO=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$REGION" \
            --query 'services[0]' \
            --output json 2>/dev/null)

        if [ -z "$SERVICE_INFO" ] || [ "$SERVICE_INFO" = "null" ]; then
            printf "  %-25s: Not found\n" "$SERVICE_NAME"
            continue
        fi

        RUNNING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.runningCount // 0')
        DESIRED_COUNT=$(echo "$SERVICE_INFO" | jq -r '.desiredCount // 0')
        PENDING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.pendingCount // 0')

        # Get CloudWatch metrics
        START_TIME=$(date -u -v-2M '+%Y-%m-%dT%H:%M:%S' 2>/dev/null || date -u -d '2 minutes ago' '+%Y-%m-%dT%H:%M:%S')
        END_TIME=$(date -u '+%Y-%m-%dT%H:%M:%S')

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

        # Format output
        TASK_INFO="$RUNNING_COUNT/$DESIRED_COUNT"
        [ "$PENDING_COUNT" -gt 0 ] && TASK_INFO="$TASK_INFO (+$PENDING_COUNT)"

        CPU_DISPLAY="${CPU_USAGE}%"
        [ "$CPU_USAGE" != "N/A" ] && [ "$CPU_USAGE" -gt 80 ] && CPU_DISPLAY="$CPU_DISPLAY ⚠️"

        MEM_DISPLAY="${MEMORY_USAGE}%"
        [ "$MEMORY_USAGE" != "N/A" ] && [ "$MEMORY_USAGE" -gt 85 ] && MEM_DISPLAY="$MEM_DISPLAY ⚠️"

        printf "  %-25s: Tasks: %-8s | CPU: %-8s | Mem: %-8s\n" \
            "$SERVICE_NAME" "$TASK_INFO" "$CPU_DISPLAY" "$MEM_DISPLAY"
    done

    echo ""
    sleep $REFRESH_INTERVAL
done
