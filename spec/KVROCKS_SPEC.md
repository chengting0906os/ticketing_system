# Kvrocks Data Storage Specification

> **📁 Related Files**: [kvrocks_client.py](../src/platform/state/kvrocks_client.py) | [atomic_reservation_executor.py](../src/service/reservation/driven_adapter/reservation_helper/atomic_reservation_executor.py) | [docker-compose.yml](../docker-compose.yml)

## Quick Reference

**Clients**: `kvrocks_client` (async), `kvrocks_client_sync` (sync)
**Config**: [.env.example](../.env.example), [core_setting.py](../src/platform/config/core_setting.py)
**Test Isolation**: Use `KVROCKS_KEY_PREFIX` env var
**Benchmark** <https://github.com/apache/kvrocks/discussions/389>

## Data Structures

| Key Pattern | Type | Purpose | Fields/Encoding |
|------------|------|---------|-----------------|
| `seats_bf:{event_id}:{section}-{subsection}` | Bitfield | Seat status (2 bits/seat) | `00`=AVAILABLE, `01`=RESERVED, `10`=SOLD |
| `event_state:{event_id}` | **JSON** | **Unified event config + stats (sections + event-level)** | See structure below |
| `booking:{booking_id}` | Hash | Booking metadata (TTL=1h) | `status`, `reserved_seats`, `total_price` |
| `event_sellout_timer:{event_id}` | Hash | Sellout time tracking | `first_ticket_reserved_at`, `fully_reserved_at`, `duration_seconds` |

### event_state JSON Structure

**✨ Unified JSON with sections + event-level stats (replaces `section_config`, `section_stats`, `event_stats` Hashes and `event_sections` index)**

```json
{
  "event_stats": {
    "available": 800,
    "reserved": 0,
    "sold": 0,
    "total": 800,
    "updated_at": 1234567890
  },
  "sections": {
    "A-1": {
      "rows": 25,
      "cols": 20,
      "price": 1000,
      "stats": {
        "available": 500,
        "reserved": 0,
        "sold": 0,
        "total": 500,
        "updated_at": 1234567890
      }
    },
    "B-1": {
      "rows": 20,
      "cols": 15,
      "price": 2000,
      "stats": {
        "available": 300,
        "reserved": 0,
        "sold": 0,
        "total": 300,
        "updated_at": 1234567890
      }
    }
  }
}
```

**Benefits**:

- 🚀 **Faster Reads**: Single `JSON.GET` fetches all sections + event stats (vs N+1 `HGETALL` calls)
- ⚛️ **Atomic Updates**: `JSON.NUMINCRBY` for both section and event stats (vs `HINCRBY`)
- 🗂️ **Unified Data**: Config + Section Stats + Event Stats in one place
- 📉 **Fewer Keys**: 1 JSON key vs 2N+2 Hash keys (section_config + section_stats + event_stats + event_sections)

## Redis Commands Reference

<https://kvrocks.apache.org/docs/supported-commands>

| Command | Category | Purpose | Example |
|---------|----------|---------|---------|
| `SETBIT key offset value` | Bitfield | Set single bit | `await client.setbit(bf_key, offset, 1)` |
| `GETBIT key offset` | Bitfield | Read single bit | `bit = await client.getbit(bf_key, offset)` |
| `GETRANGE key start end` | Bitfield | Batch read bitfield | `bytes = await client.getrange(bf_key, 0, 999)` |
| **`JSON.GET key path`** | **JSON** | **Get JSON document** | `await client.execute_command('JSON.GET', key, '$')` |
| **`JSON.SET key path value`** | **JSON** | **Set JSON document** | `await client.execute_command('JSON.SET', key, '$', json_str)` |
| **`JSON.NUMINCRBY key path value`** | **JSON** | **Atomic number increment** | `pipe.execute_command('JSON.NUMINCRBY', key, "$.sections['A-1'].stats.available", -1)` |
| `HSET key field value` | Hash | Set single field | `client.hset(key, 'price', '1000')` |
| `HSET key mapping={...}` | Hash | Set multiple fields | `await client.hset(key, mapping={'a': '1'})` |
| `HSETNX key field value` | Hash | Set if field not exists | `pipe.hsetnx(timer_key, 'first_ticket_reserved_at', now)` |
| `HGET key field` | Hash | Get single field | `price = await client.hget(meta_key, '1')` |
| `HGETALL key` | Hash | Get all fields | `config = await client.hgetall(config_key)` |
| `HINCRBY key field increment` | Hash | Atomic counter | `pipe.hincrby(stats_key, 'available', -1)` |
| `ZADD key score member` | Sorted Set | Add to index | `await client.zadd(index_key, {id: 0})` |
| `ZRANGE key start stop` | Sorted Set | Get all members | `ids = await client.zrange(key, 0, -1)` |
| `DELETE key` | Key Mgmt | Delete key | `await client.delete(booking_key)` |
| `EXPIRE key seconds` | Key Mgmt | Set TTL | `pipe.expire(booking_key, 3600)` |
| `KEYS pattern` | Key Mgmt | Find keys | `keys = await client.keys('event_state:*')` |
| `pipeline()` | Transaction | Batch commands | `pipe = client.pipeline()` |
| `pipeline(transaction=True)` | Transaction | MULTI/EXEC | `pipe = client.pipeline(transaction=True)` |
| `execute()` | Transaction | Execute pipeline | `results = await pipe.execute()` |

When using `JSON.GET key $` (JSONPath query), **Kvrocks returns `str` (JSON string)**:

```python
# Real Kvrocks Output (tested with Kvrocks 2.x)
client = kvrocks_client.get_client()
result = await client.execute_command('JSON.GET', 'event_state:1', '$')  # '$' = JSONPath root selector (get entire JSON)

# result = '[{"event_stats": {...}, "sections": {...}}]'
# Type: str (JSON array string)

# Parse JSON array and extract first element
event_state_list = orjson.loads(result)  # Parse JSON string to list
event_state = event_state_list[0]  # Get first object from array
```

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
8. **HSETNX for time tracking**: Atomic first-write-wins semantics

## Sellout Time Tracking

> **Implementation**: [atomic_reservation_executor.py:56-159](../src/service/reservation/driven_adapter/reservation_helper/atomic_reservation_executor.py#L56-L159)

### Overview

Tracks the time from first ticket sold to complete sellout for performance analysis and business metrics.

### Data Structure

```redis
HGETALL event_sellout_timer:123
1) "first_ticket_reserved_at"
2) "2025-11-05T10:30:15.123456+00:00"    # ISO 8601 timestamp
3) "fully_reserved_at"
4) "2025-11-05T10:35:42.789012+00:00"    # When available reached 0
5) "duration_seconds"
6) "327.665556"                           # Calculated duration (seconds)
```

### Why HSETNX Instead of HSET?

**Critical Design Choice**: Use `HSETNX` (Hash Set if Not eXists) to track the first ticket.

#### ✅ Correct: HSETNX

```python
pipe.hsetnx(timer_key, 'first_ticket_reserved_at', now)
```

**Guarantees**:

- ✅ **Atomic**: Only sets if field doesn't exist
- ✅ **Idempotent**: Safe to call multiple times
- ✅ **First-write-wins**: Records the actual first ticket timestamp
- ✅ **Concurrent-safe**: Even with race conditions, only first succeeds
- ✅ **Return value**: 1 if set, 0 if already exists

#### ❌ Wrong: HSET

```python
pipe.hset(timer_key, 'first_ticket_reserved_at', now)  # DON'T DO THIS
```

**Problems**:

- ❌ **Overwrites**: Later requests overwrite earlier timestamps
- ❌ **Race conditions**: Concurrent requests cause wrong timestamp
- ❌ **Data corruption**: Can't guarantee first ticket time

### Implementation Details

#### 1. Read Current State (Before Pipeline)

```python
# STEP 0: Check if this is the first ticket (read from unified JSON)
config_key = _make_key(f'event_state:{event_id}')
result = await client.execute_command('JSON.GET', config_key, '$.event_stats')

# result = '[{"available":500,"reserved":0,...}]' (JSON array string)
event_stats_list = orjson.loads(result)  # Parse JSON string
current_stats = event_stats_list[0]  # Get first element
current_reserved_count = int(current_stats.get('reserved', 0))
```

**Why read before pipeline?**

- Pipeline can't read values (only queue commands)
- Need `current_reserved_count` to decide if this is first ticket
- Kafka partitioning ensures sequential processing per event

#### 2. Track First Ticket (In Pipeline)

```python
async def _track_first_ticket(*, current_reserved_count, ...):
    if current_reserved_count == 0:  # Only first ticket
        timer_key = f'event_sellout_timer:{event_id}'
        now = datetime.now(timezone.utc).isoformat()
        pipe.hsetnx(timer_key, 'first_ticket_reserved_at', now)
```

**Key points**:

- Only executes when `reserved == 0`
- Uses `HSETNX` for atomic first-write
- Timestamp in ISO 8601 format
- Part of MULTI/EXEC transaction

#### 3. Track Sold Out (After Pipeline)

```python
async def _track_sellout_complete(*, new_available_count, ...):
    if new_available_count == 0:  # Just sold out
        first_time = await client.hget(timer_key, 'first_ticket_reserved_at')
        fully_reserved_at = datetime.now(timezone.utc)
        duration = (fully_reserved_at - parse(first_time)).total_seconds()

        await client.hset(timer_key, mapping={
            'fully_reserved_at': fully_reserved_at.isoformat(),
            'duration_seconds': str(duration),
        })
```

### Concurrency Handling

#### Scenario: Two Requests Arrive Simultaneously

```plain
Timeline:
──────────────────────────────────────────────────────────

Request A (10:30:15.100):
  ├─ Read: current_reserved_count = 0  ✅
  ├─ Check: 0 == 0  ✅ Is first ticket
  ├─ HSETNX first_ticket_reserved_at = '10:30:15.100'
  └─ EXEC → SUCCESS (field created)  ✅

Request B (10:30:15.120, almost same time):
  ├─ Read: current_reserved_count = 0  ✅ (A not committed yet)
  ├─ Check: 0 == 0  ✅ Thinks it's first ticket
  ├─ HSETNX first_ticket_reserved_at = '10:30:15.120'
  └─ EXEC → IGNORED (field exists)  ✅

Result: first_ticket_reserved_at = '10:30:15.100' (Request A) ✅
```
