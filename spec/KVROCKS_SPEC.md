# Kvrocks Data Storage Specification

> **📁 Related Files**: [kvrocks_client.py](../src/platform/state/kvrocks_client.py) | [atomic_reservation_executor.py](../src/service/seat_reservation/driven_adapter/seat_reservation_helper/atomic_reservation_executor.py) | [docker-compose.yml](../docker-compose.yml)

## Quick Reference

**Clients**: `kvrocks_client` (async), `kvrocks_client_sync` (sync)
**Config**: [.env.example](../.env.example), [core_setting.py](../src/platform/config/core_setting.py)
**Test Isolation**: Use `KVROCKS_KEY_PREFIX` env var

## Data Structures

| Key Pattern | Type | Purpose | Fields/Encoding |
|------------|------|---------|-----------------|
| `seats_bf:{event_id}:{section}-{subsection}` | Bitfield | Seat status (2 bits/seat) | `00`=AVAILABLE, `01`=RESERVED, `10`=SOLD |
| `section_config:{event_id}:{section}-{subsection}` | Hash | Section layout | `rows`, `seats_per_row` |
| `section_stats:{event_id}:{section}-{subsection}` | Hash | Section statistics | `available`, `reserved`, `sold`, `total` |
| `seat_meta:{event_id}:{section}-{subsection}:{row}` | Hash | Seat metadata (per row) | `{seat_num}` → JSON with `price`, `booking_id` |
| `event_sections:{event_id}` | Sorted Set | Section index | Section IDs (score=0) |
| `booking:{booking_id}` | Hash | Booking metadata (TTL=1h) | `status`, `reserved_seats`, `total_price` |
| `event_stats:{event_id}` | Hash | Event-level statistics | `available`, `reserved`, `sold`, `total` |

## Redis Commands Reference

<https://kvrocks.apache.org/docs/supported-commands>

| Command | Category | Purpose | Example |
|---------|----------|---------|---------|
| `SETBIT key offset value` | Bitfield | Set single bit | `await client.setbit(bf_key, offset, 1)` |
| `GETBIT key offset` | Bitfield | Read single bit | `bit = await client.getbit(bf_key, offset)` |
| `GETRANGE key start end` | Bitfield | Batch read bitfield | `bytes = await client.getrange(bf_key, 0, 999)` |
| `HSET key field value` | Hash | Set single field | `client.hset(key, 'price', '1000')` |
| `HSET key mapping={...}` | Hash | Set multiple fields | `await client.hset(key, mapping={'a': '1'})` |
| `HGET key field` | Hash | Get single field | `price = await client.hget(meta_key, '1')` |
| `HGETALL key` | Hash | Get all fields | `config = await client.hgetall(config_key)` |
| `HINCRBY key field increment` | Hash | Atomic counter | `pipe.hincrby(stats_key, 'available', -1)` |
| `ZADD key score member` | Sorted Set | Add to index | `await client.zadd(index_key, {id: 0})` |
| `ZRANGE key start stop` | Sorted Set | Get all members | `ids = await client.zrange(key, 0, -1)` |
| `DELETE key` | Key Mgmt | Delete key | `await client.delete(booking_key)` |
| `EXPIRE key seconds` | Key Mgmt | Set TTL | `pipe.expire(booking_key, 3600)` |
| `KEYS pattern` | Key Mgmt | Find keys | `keys = await client.keys('event_sections:*')` |
| `pipeline()` | Transaction | Batch commands | `pipe = client.pipeline()` |
| `pipeline(transaction=True)` | Transaction | MULTI/EXEC | `pipe = client.pipeline(transaction=True)` |
| `execute()` | Transaction | Execute pipeline | `results = await pipe.execute()` |

## Transaction & Isolation

### MULTI/EXEC Guarantees

| Feature | MULTI/EXEC | MULTI/EXEC + Kvrocks WAL |
|---------|------------|--------------------------|
| **Isolation** | ✅ Commands don't interleave | ✅ Same |
| **Rollback** | ❌ No automatic rollback | ❌ No automatic rollback |
| **Durability** | ❌ Depends on persistence | ✅ WAL ensures crash recovery |

### Why This Works

**Three-Layer Guarantee**:

1. **Application**: Kafka partitioning → same `booking_id` → same partition → no concurrent updates
2. **Redis**: MULTI/EXEC → isolated execution without interleaving
3. **Storage**: RocksDB WAL → crash recovery and durability

**Result**: No need for WATCH/retry loops. Kafka consumer retries on crash.

### Atomic Reservation Pattern

```python
pipe = client.pipeline(transaction=True)  # Enable MULTI/EXEC
# Update bitfield
pipe.setbit(bf_key, offset, 0)
pipe.setbit(bf_key, offset + 1, 1)
# Update stats
pipe.hincrby(stats_key, 'available', -1)
pipe.hincrby(stats_key, 'reserved', 1)
# Fetch stats
pipe.hgetall(stats_key)
# Save metadata
pipe.hset(booking_key, mapping={...})
await pipe.execute()  # All commands commit atomically
```

## Client Usage

### Async (HTTP Controllers)

```python
from src.platform.state.kvrocks_client import kvrocks_client

# In startup
await kvrocks_client.initialize()

# In handlers
client = kvrocks_client.get_client()
await client.setbit(...)
```

### Sync (Kafka Consumers)

```python
from src.platform.state.kvrocks_client import kvrocks_client_sync

# In startup
client = kvrocks_client_sync.connect()

# In consumer
client.setbit(...)
```

## Performance Optimizations

1. **GETRANGE vs GETBIT**: 1 command instead of N (20×50 section: 2000 → 1 call)
2. **HINCRBY**: Atomic counters without read-modify-write
3. **Pipeline**: Batch commands to reduce network round-trips
4. **Connection Pool**: 10-100x lower latency (reuse connections)
5. **2-bit encoding**: 400x storage reduction vs individual keys

## Test Isolation

```python
# Use environment variable for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')

def _make_key(key: str) -> str:
    return f'{_KEY_PREFIX}{key}'

# Production: seats_bf:1:A-1
# Test:       test_gw0_seats_bf:1:A-1
```

**Critical**: All Kvrocks operations must use `_make_key()` wrapper

## Key Design Decisions

1. **Bitfield over individual keys**: 400x storage reduction
2. **2-bit encoding**: Supports 4 states with minimal space
3. **Row-based metadata**: 1 key per row (balance between granularity and key count)
4. **Sorted set for index**: Fast O(log N) section lookup
5. **MULTI/EXEC for writes**: Isolation without WATCH complexity
6. **Kvrocks over Redis**: RocksDB WAL for zero data loss
7. **Connection pooling**: Performance and resource control
