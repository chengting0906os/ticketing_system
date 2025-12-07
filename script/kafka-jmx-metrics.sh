#!/bin/bash
# =============================================================================
# Kafka JMX Metrics Query Script
# Query key broker metrics via JMX to diagnose latency issues
# =============================================================================
#
# Usage: ./kafka-jmx-metrics.sh [broker]
#   broker: kafka1, kafka2, or kafka3 (default: all)
#
# Key Metrics Interpretation:
#   RequestHandlerAvgIdlePercent: > 50% OK, < 30% = CPU overload
#   RequestQueueTimeMs: High = broker request queue backed up
#   LocalTimeMs: High = disk I/O flush slow
#   TotalTimeMs: End-to-end produce request time
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

query_broker_metrics() {
    local broker=$1
    local jmx_port=$2

    echo -e "${YELLOW}=== Broker: ${broker} (JMX port: ${jmx_port}) ===${NC}"

    # RequestHandlerAvgIdlePercent
    echo -e "${GREEN}1. Request Handler Idle Percent:${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.server:type=KafkaRequestHandlerPool,name=RequestHandlerAvgIdlePercent" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   OneMinuteRate: %.2f%%\n", $7*100}'

    # Produce RequestQueueTimeMs
    echo -e "${GREEN}2. Produce Request Queue Time (ms):${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.network:type=RequestMetrics,name=RequestQueueTimeMs,request=Produce" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   Mean: %.2f, Max: %.2f, P99: %.2f\n", $4, $5, $9}'

    # Produce LocalTimeMs
    echo -e "${GREEN}3. Produce Local Time (ms) - Disk I/O:${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.network:type=RequestMetrics,name=LocalTimeMs,request=Produce" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   Mean: %.2f, Max: %.2f, P99: %.2f\n", $4, $5, $9}'

    # Produce TotalTimeMs
    echo -e "${GREEN}4. Produce Total Time (ms) - End-to-End:${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   Mean: %.2f, Max: %.2f, P99: %.2f\n", $4, $5, $9}'

    # Fetch RequestQueueTimeMs (Consumer)
    echo -e "${GREEN}5. Fetch Request Queue Time (ms) - Consumer:${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.network:type=RequestMetrics,name=RequestQueueTimeMs,request=Fetch" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   Mean: %.2f, Max: %.2f, P99: %.2f\n", $4, $5, $9}'

    # Fetch TotalTimeMs (Consumer)
    echo -e "${GREEN}6. Fetch Total Time (ms) - Consumer:${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Fetch" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   Mean: %.2f, Max: %.2f, P99: %.2f\n", $4, $5, $9}'

    # Log Flush Rate and Time
    echo -e "${GREEN}7. Log Flush Rate and Time:${NC}"
    docker exec ${broker} kafka-run-class kafka.tools.JmxTool \
        --jmx-url "service:jmx:rmi:///jndi/rmi://${broker}:${jmx_port}/jmxrmi" \
        --object-name "kafka.log:type=LogFlushStats,name=LogFlushRateAndTimeMs" \
        --one-time true 2>/dev/null | tail -1 | awk -F',' '{printf "   Mean: %.2fms, Max: %.2fms, Count: %d\n", $4, $5, $2}'

    echo ""
}

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}  Kafka JMX Metrics - Broker Latency Diagnostics${NC}"
echo -e "${CYAN}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}======================================================${NC}"
echo ""

BROKER=${1:-all}

if [ "$BROKER" = "all" ]; then
    query_broker_metrics "kafka1" "9991"
    query_broker_metrics "kafka2" "9992"
    query_broker_metrics "kafka3" "9993"
else
    case $BROKER in
        kafka1) query_broker_metrics "kafka1" "9991" ;;
        kafka2) query_broker_metrics "kafka2" "9992" ;;
        kafka3) query_broker_metrics "kafka3" "9993" ;;
        *) echo "Unknown broker: $BROKER"; exit 1 ;;
    esac
fi

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}  Interpretation Guide${NC}"
echo -e "${CYAN}======================================================${NC}"
echo -e "${GREEN}RequestHandlerAvgIdlePercent:${NC}"
echo "  > 50% = OK, < 30% = CPU overload (need more request handlers)"
echo ""
echo -e "${GREEN}RequestQueueTimeMs:${NC}"
echo "  High value = broker request queue is backed up (slow processing)"
echo ""
echo -e "${GREEN}LocalTimeMs:${NC}"
echo "  High value = disk I/O flush is slow (storage bottleneck)"
echo ""
echo -e "${GREEN}TotalTimeMs:${NC}"
echo "  End-to-end request time (includes network + queue + local time)"
echo ""
echo -e "${GREEN}LogFlushRateAndTimeMs:${NC}"
echo "  High value = disk flush taking too long (may cause latency spikes)"
