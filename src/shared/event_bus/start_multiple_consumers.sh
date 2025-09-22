#!/bin/bash

# Multiple Kafka Consumer Startup Script
# For testing unified logging system

echo "🚀 Starting multiple Kafka consumer instances for testing..."
echo "🔍 Each consumer has a unique identifier, all logs are centralized to the same file"
echo ""

# Number of consumers
CONSUMER_COUNT=${1:-3}

echo "📊 Preparing to start $CONSUMER_COUNT consumer instances"
echo "📝 All logs will output to: logs/$(date '+%Y-%m-%d_%H').log"
echo ""

# Store background process PIDs
PIDS=()

# Start multiple consumer instances
for i in $(seq 1 $CONSUMER_COUNT); do
    echo "🔄 Starting consumer instance #$i..."

    # Start consumer in background
    uv run python -m src.shared.event_bus.start_unified_consumers &

    # Record PID
    PID=$!
    PIDS+=($PID)

    echo "   ✅ Consumer #$i started (PID: $PID)"

    # Small delay to avoid simultaneous startup competition
    sleep 2
done

echo ""
echo "🎉 All consumers started!"
echo "📋 Consumer process list:"
for i in "${!PIDS[@]}"; do
    PID=${PIDS[$i]}
    echo "   Consumer #$((i+1)): PID $PID"
done

echo ""
echo "🔧 Management commands:"
echo "   Stop all consumers: kill ${PIDS[*]}"
echo "   View logs: tail -f logs/$(date '+%Y-%m-%d_%H').log"
echo "   View colored logs: tail -f logs/$(date '+%Y-%m-%d_%H').log | grep -E '\\[CONSUMER-|📨|🔄|🎉|❌'"
echo ""

# Wait for user interruption
echo "⏳ Press Ctrl+C to stop all consumers..."
trap 'echo ""; echo "🛑 Stopping all consumers..."; kill ${PIDS[*]} 2>/dev/null; echo "✅ All consumers stopped"; exit 0' INT

# Keep running
while true; do
    sleep 1
done