# Kvrocks Data Storage Specification

> **📁 Related Files**: [kvrocks_client.py](../src/platform/state/kvrocks_client.py) | [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py) | [docker-compose.yml](../docker-compose.yml)

## Infrastructure Setup

See [docker-compose.yml](../docker-compose.yml) for deployment config

**Connection Settings**: See [kvrocks_client.py](../src/platform/state/kvrocks_client.py)

- **Async Client**: `KvrocksClient` - For HTTP controllers (explicit `ConnectionPool`)
- **Sync Client**: `KvrocksClientSync` - For Kafka consumers (internal `ConnectionPool`)

**Connection Pool Configuration**: See [.env.example](../.env.example) and [core_setting.py](../src/platform/config/core_setting.py)

- `KVROCKS_POOL_MAX_CONNECTIONS=50` - Maximum connections in pool
- `KVROCKS_POOL_SOCKET_TIMEOUT=5` - Socket read/write timeout (seconds)
- `KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT=5` - Connection timeout (seconds)
- `KVROCKS_POOL_SOCKET_KEEPALIVE=true` - Enable TCP keepalive
- `KVROCKS_POOL_HEALTH_CHECK_INTERVAL=30` - Health check interval (seconds)

## Data Structures

### 1. Bitfield - Seat Status

See [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py):

**Key Pattern**: `seats_bf:{event_id}:{section}-{subsection}`

**Encoding** (2 bits per seat):

- `0b00` (0) = `SEAT_STATUS_AVAILABLE`
- `0b01` (1) = `SEAT_STATUS_RESERVED`
- `0b10` (2) = `SEAT_STATUS_SOLD`

**Storage Efficiency**:

- 100 seats = 25 bytes
- 500 seats = 125 bytes
- 10,000 seats = 2.5 KB

**Seat Index Calculation**: See [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py) `_calculate_seat_index()`

**Read Operations**: See [kvrocks_client.py](../src/platform/state/kvrocks_client.py)

- Single seat: `BITFIELD GET u2 #{offset}`
- Batch read: `GETRANGE` - Reads raw bytes, decode to 2-bit values

### 2. Section Configuration

See [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py):

**Key Pattern**: `section_config:{event_id}:{section}-{subsection}`

**Type**: Hash

**Fields**: `rows`, `seats_per_row`

**Operations**:

- Get: `_get_section_config()` - With LRU cache
- Save: `_save_section_config()` - `HSET`

### 3. Section Statistics

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py):

**Key Pattern**: `section_stats:{event_id}:{section}-{subsection}`

**Type**: Hash

**Fields**: `section_id`, `event_id`, `available`, `reserved`, `sold`, `total`, `updated_at`

**Query**: `list_all_subsection_status()` - Uses pipeline for batch reads

### 4. Seat Metadata

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py):

**Key Pattern**: `seat_meta:{event_id}:{section}-{subsection}:{row}`

**Type**: Hash (one hash per row)

**Fields**: `{seat_num}` → JSON with `buyer_id`, `booking_id`, `price`, `reserved_at`

**Design**: Row-based grouping (1 key per row, not per seat or per section)

### 5. Event Section Index

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py):

**Key Pattern**: `event_sections:{event_id}`

**Type**: Sorted Set (score=0, used as set)

**Purpose**: Fast lookup of all sections in an event

**Usage**: Batch query all section stats for event listing UI

## Atomic Operations

All operations use Redis Pipeline for atomicity.

### Reserve Seats (0b00 → 0b01)

Example implementation pattern:

```python
pipe = client.pipeline()
# 1. Update bitfield
pipe.bitfield(key).set('u2', offset, SEAT_STATUS_RESERVED)
# 2. Update stats
pipe.hincrby(stats_key, 'available', -1)
pipe.hincrby(stats_key, 'reserved', 1)
# 3. Save metadata
pipe.hset(meta_key, seat_num, json.dumps({...}))
await pipe.execute()  # All or nothing
```

### Finalize to Sold (0b01 → 0b10)

Similar pattern with `SEAT_STATUS_SOLD`

### Release Seats (0b01 → 0b00)

Similar pattern + `HDEL` metadata

## Test Isolation Strategy

See [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py):

**Environment Variable**: `KVROCKS_KEY_PREFIX`

```python
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')

def _make_key(key: str) -> str:
    return f'{_KEY_PREFIX}{key}'
```

**Usage**:

- Production: `seats_bf:1:A-1`
- Test: `test_gw0_seats_bf:1:A-1`

**Critical**: All Kvrocks operations must use `_make_key()` wrapper

## Performance Characteristics

| Operation | Latency | Method |
|-----------|---------|--------|
| Single seat read | < 0.1ms | `BITFIELD GET` |
| 100 seats read | < 1ms | `GETRANGE` (25 bytes) |
| 500 seats read | < 2ms | `GETRANGE` (125 bytes) |
| Section stats | < 0.5ms | `HGETALL` |
| Reserve 1 seat | < 2ms | Pipeline (3 commands) |
| Reserve 4 seats | < 3ms | Pipeline (6 commands) |

**Storage vs SQL**: 400x reduction (100 seats: 25 bytes vs ~10 KB)

## Client Implementation

### Async Client

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py) `KvrocksClient`:

```python
from src.platform.state.kvrocks_client import kvrocks_client

client = await kvrocks_client.connect()  # Creates ConnectionPool on first call
await client.bitfield(...).execute()
await kvrocks_client.disconnect()  # Closes client and pool
```

**Connection Pool Details**:

- Uses explicit `redis.asyncio.ConnectionPool` with configurable `max_connections`
- Pool is created once and reused for all operations
- Supports automatic health checks via `health_check_interval`
- Handles event loop changes gracefully (important for testing)

### Sync Client

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py) `KvrocksClientSync`:

```python
from src.platform.state.kvrocks_client import kvrocks_client_sync

client = kvrocks_client_sync.connect()  # Internal ConnectionPool created by redis.from_url
client.bitfield(...).execute()
kvrocks_client_sync.disconnect()  # Closes client
```

**Connection Pool Details**:

- `redis.from_url()` automatically creates internal `ConnectionPool`
- Pool settings (max_connections, timeouts) passed directly to `from_url()`
- Simpler than explicit pool management (YAGNI principle)
- Ideal for Kafka consumers - no need for BlockingConnectionPool complexity

### Stats Client (Legacy)

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py):

- `list_all_subsection_status()`
- `list_subsection_seats_detail()`

## Connection Pooling Benefits

### Why Connection Pooling Matters

**Without pooling**: Each operation creates a new TCP connection, causing:

- High latency (TCP handshake: ~1-3ms per connection)
- Resource exhaustion (file descriptors, memory)
- Poor performance under load

**With pooling**: Connections are reused, providing:

- **10-100x lower latency**: No handshake overhead
- **Better resource control**: Bounded connection count
- **Automatic health checks**: Stale connections auto-recycled
- **Simpler code**: Internal pools managed automatically by redis-py

### Pool Configuration Guidelines

| Scenario | max_connections | Rationale |
|----------|----------------|-----------|
| Single service | 10-20 | Sufficient for typical workloads |
| High concurrency | 50-100 | Handle traffic spikes |
| Kafka consumers | 20-50 | Balance throughput vs resources |

**Health Check Interval**:

- Default: 30 seconds
- High traffic: 10-15 seconds (catch issues faster)
- Low traffic: 60 seconds (reduce overhead)

**Socket Timeouts**:

- `socket_connect_timeout`: 5s (fail fast on network issues)
- `socket_timeout`: 5s (detect hung connections)

### Best Practices

1. **Always use singleton clients**: `kvrocks_client` and `kvrocks_client_sync` are global singletons
2. **Call `connect()` at startup**: Warm up the pool before handling requests
3. **Call `disconnect()` at shutdown**: Clean up resources gracefully
4. **Monitor pool exhaustion**: Watch for `ConnectionError` in logs
5. **Tune max_connections**: Based on load testing and resource monitoring

## Key Design Decisions

1. **Bitfield over individual keys**: 400x storage reduction, sub-millisecond reads
2. **2-bit encoding**: Supports 4 states with minimal space
3. **Row-based metadata**: 1 key per row (not per seat, not per section)
4. **Sorted set for index**: Fast O(log N) section lookup
5. **Pipeline for atomicity**: Multiple operations in single transaction
6. **Test isolation via prefix**: Parallel test execution without conflicts
7. **Kvrocks over Redis**: Persistent storage with zero data loss (RocksDB backend)
8. **Sync + Async clients**: Supports both HTTP (async) and Kafka (sync) contexts
9. **Connection pooling**: Explicit pool configuration for performance and resource control
