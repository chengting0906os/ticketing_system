# Kvrocks Data Storage Specification

> **📁 Related Files**: [kvrocks_client.py](../src/platform/state/kvrocks_client.py) | [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py) | [docker-compose.yml](../docker-compose.yml)

## Infrastructure Setup

See [docker-compose.yml](../docker-compose.yml) for deployment config

**Connection Settings**: See [kvrocks_client.py](../src/platform/state/kvrocks_client.py)
- **Async Client**: `KvrocksClient` - For HTTP controllers
- **Sync Client**: `KvrocksClientSync` - For Kafka consumers

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

client = await kvrocks_client.connect()
await client.bitfield(...).execute()
await kvrocks_client.disconnect()
```

### Sync Client

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py) `KvrocksClientSync`:
```python
from src.platform.state.kvrocks_client import kvrocks_client_sync

client = kvrocks_client_sync.connect()
client.bitfield(...).execute()
kvrocks_client_sync.disconnect()
```

### Stats Client (Legacy)

See [kvrocks_client.py](../src/platform/state/kvrocks_client.py):
- `list_all_subsection_status()`
- `list_subsection_seats_detail()`

## Key Design Decisions

1. **Bitfield over individual keys**: 400x storage reduction, sub-millisecond reads
2. **2-bit encoding**: Supports 4 states with minimal space
3. **Row-based metadata**: 1 key per row (not per seat, not per section)
4. **Sorted set for index**: Fast O(log N) section lookup
5. **Pipeline for atomicity**: Multiple operations in single transaction
6. **Test isolation via prefix**: Parallel test execution without conflicts
7. **Kvrocks over Redis**: Persistent storage with zero data loss (RocksDB backend)
8. **Sync + Async clients**: Supports both HTTP (async) and Kafka (sync) contexts
