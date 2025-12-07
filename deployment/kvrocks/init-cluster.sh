#!/bin/bash
# =============================================================================
# KVRocks Cluster Initialization Script
# Sets up 4-node cluster with 16384 slots distributed evenly
# =============================================================================

set -e

echo "⏳ Waiting for all KVRocks nodes to be ready..."
sleep 5

# Node IDs (40 characters each)
NODE1_ID="0000000000000000000000000000000000000001"
NODE2_ID="0000000000000000000000000000000000000002"
NODE3_ID="0000000000000000000000000000000000000003"
NODE4_ID="0000000000000000000000000000000000000004"

# Slot distribution (16384 total slots)
# Node 1: 0-4095     (Section A-C roughly, based on hash)
# Node 2: 4096-8191  (Section C-F)
# Node 3: 8192-12287 (Section F-H)
# Node 4: 12288-16383 (Section H-J)

echo "🔧 Setting node IDs..."
redis-cli -h kvrocks-1 -p 6666 CLUSTERX SETNODEID $NODE1_ID
redis-cli -h kvrocks-2 -p 6666 CLUSTERX SETNODEID $NODE2_ID
redis-cli -h kvrocks-3 -p 6666 CLUSTERX SETNODEID $NODE3_ID
redis-cli -h kvrocks-4 -p 6666 CLUSTERX SETNODEID $NODE4_ID

echo "📊 Configuring cluster topology..."

# Cluster topology string (all services run in Docker network)
TOPOLOGY="$NODE1_ID kvrocks-1 6666 master - 0-4095
$NODE2_ID kvrocks-2 6666 master - 4096-8191
$NODE3_ID kvrocks-3 6666 master - 8192-12287
$NODE4_ID kvrocks-4 6666 master - 12288-16383"

# Apply topology to all nodes (version 1)
echo "🚀 Applying topology to all nodes..."
redis-cli -h kvrocks-1 -p 6666 CLUSTERX SETNODES "$TOPOLOGY" 1
redis-cli -h kvrocks-2 -p 6666 CLUSTERX SETNODES "$TOPOLOGY" 1
redis-cli -h kvrocks-3 -p 6666 CLUSTERX SETNODES "$TOPOLOGY" 1
redis-cli -h kvrocks-4 -p 6666 CLUSTERX SETNODES "$TOPOLOGY" 1

echo "✅ Verifying cluster status..."
redis-cli -h kvrocks-1 -p 6666 CLUSTER NODES
redis-cli -h kvrocks-1 -p 6666 CLUSTER INFO

echo ""
echo "✅ KVRocks Cluster initialized successfully!"
echo "   Nodes: kvrocks-1:6666, kvrocks-2:6666, kvrocks-3:6666, kvrocks-4:6666"
echo "   Slots: 4096 per node (16384 total)"
