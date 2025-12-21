# Seat Reservation Strategy

**Version:** 1.0 | **Updated:** 2025-11-21

## Overview

Kvrocks-based seat reservation system with:

- **Performance**: Lua scripts + Redis pipelines (99.6% round-trip reduction)
- **Atomicity**: MULTI/EXEC transactions
- **User Experience**: Consecutive seat finding with smart fallback

### Modes

1. **Manual**: User selects specific seats
2. **Best Available**: Auto-find N consecutive seats

---

## Kvrocks Data Structures

### 1. Seat Bitfield (`seats_bf:{event_id}:{section_id}`)

**Encoding:** 2 bits per seat

- `00` = AVAILABLE (0)
- `01` = RESERVED (1)

> **Note**: SOLD 狀態 (`10`) 不再使用。付款後座位保持 RESERVED 直到釋放。PostgreSQL 是 ticket 狀態的 source of truth。

**Index Calculation:**

```python
seat_index = (row - 1) * cols + (seat_num - 1)
bit_offset = seat_index * 2
```

**Operations:**
u2 = Unsigned 2-bit integer

```bash
BITFIELD seats_bf:123:A-1 GET u2 <offset>    # Read
BITFIELD seats_bf:123:A-1 SET u2 <offset> 1  # Reserve
```

### 2. Event State JSON (`event_state:{event_id}`)

```json
{
  "event_stats": {"available": 498, "reserved": 2, "sold": 0, "total": 500},
  "sections": {
    "A": {
      "price": 3000,
      "subsections": {
        "1": {"rows": 25, "cols": 20, "stats": {...}}
      }
    }
  }
}
```

**Operations:**

```bash
JSON.GET event_state:123 $
JSON.NUMINCRBY event_state:123 $.event_stats.reserved 2
```

### 3. Availability Counters

**Subsection:** `seats_avail:{event_id}:{section_id}`
**Row-level:** `seats_avail_row:{event_id}:{section_id}:{row}`

Used for Lua script optimization (skip full rows → 97% reduction)

### 4. Booking Metadata (`booking:{booking_id}`)

```text
status: "RESERVE_SUCCESS" | "RESERVE_FAILED"
reserved_seats: ["1-1", "1-2"]
total_price: "6000"
```

### 5. Sellout Timer (`event_sellout_timer:{event_id}`)

Tracks time-to-sellout metrics.

---

## Visual Example: 5x5 Seat Layout

> **Note**: 以下範例展示 2-bit 設計，但實際上 SOLD (`10`) 狀態不再使用。Kvrocks 只追蹤 AVAILABLE/RESERVED。

**State Transition (Reserve Seats 1-2 in Row 2):**

```text
Before:                          After:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bitfield (Row 2):
Offset: 10  12  14  16  18       10  12  14  16  18
Value:  00  00  00  00  00  →    01  01  00  00  10
        🟢  🟢   🟢  🟢  🟢        🟡  🟡   🟢  🟢   🔴
        S1  S2  S3  S4  S5       S1  S2  S3  S4  S5

Seat Map (showing all 3 states):
Row 1:  🟢 🟢 🟢 🟢 🟢  →    Row 1:  🟢 🟢 🟢 🟢 🟢  ← Available (00)
Row 2:  🟢 🟢 🟢 🟢 🟢  →    Row 2:  🟡 🟡 🟢 🟢 🔴  ← Reserved (01) + Sold (10)
Row 3:  🟢 🟢 🟢 🟢 🟢  →    Row 3:  🔴 🟢 🟢 🟢 🟢  ← Sold (10)
Row 4:  🟢 🟢 🟢 🟢 🟢  →    Row 4:  🟢 🟢 🟢 🟢 🟢 
Row 5:  🟢 🟢 🟢 🟢 🟢  →    Row 5:  🟢 🟢 🟢 🟢 🟢 

Bitfield Values:
- Row 2, Seat 1-2: 00 → 01 (AVAILABLE → RESERVED)
- Row 3, Seat 1:   00 → 10 (AVAILABLE → SOLD)

Counters:
seats_avail:123:A-1           25 → 22 (reserved 2, sold 1)
seats_avail_row:123:A-1:2      5 → 2  (2 reserved, 1 sold)
seats_avail_row:123:A-1:3      5 → 4  (1 sold)

Event Stats:
available                     25 → 21
reserved                       0 → 2
sold                           0 → 2
```

**Final Kvrocks State:**

```text
┌─────────────────────────────────────────────────┐
│ Key                       │ Value               │
├─────────────────────────────────────────────────┤
│ seats_bf:123:A-1          │ Bitfield (2→01)     │
│ seats_avail:123:A-1       │ 23                  │
│ seats_avail_row:123:A-1:1 │ 5                   │
│ seats_avail_row:123:A-1:2 │ 3 ⬇️                │
│ seats_avail_row:123:A-1:3 │ 5                   │
│ seats_avail_row:123:A-1:4 │ 5                   │
│ seats_avail_row:123:A-1:5 │ 5                   │
│ event_state:123           │ JSON (updated)      │
│ booking:01JDB...          │ Hash (new)          │
└─────────────────────────────────────────────────┘
```

**Complete Bitfield Memory After Reservation:**

**Row 1 Detail (all available):**

| Position | Seat 1 | Seat 2 | Seat 3 | Seat 4 | Seat 5 |
|----------|--------|--------|--------|--------|--------|
| Index    | 0      | 1      | 2      | 3      | 4      |
| Offset   | 0      | 2      | 4      | 6      | 8      |
| Value    | 00     | 00     | 00     | 00     | 00     |
| Status   | 🟢     | 🟢     | 🟢     | 🟢     | 🟢     |

**Row 2 Detail (showing all 3 states):**

| Position | **Seat 1** | **Seat 2** | Seat 3 | Seat 4 | **Seat 5** |
|----------|------------|------------|--------|--------|------------|
| Index    | **5**      | **6**      | 7      | 8      | **9**      |
| Offset   | **10**     | **12**     | 14     | 16     | **18**     |
| Value    | **01**     | **01**     | 00     | 00     | **10**     |
| Status   | **🟡**     | **🟡**     | 🟢     | 🟢     | **🔴**     |

**Explanation:**

- **Seat 1-2**: `01` = RESERVED 🟡
- **Seat 3-4**: `00` = AVAILABLE 🟢
- **Seat 5**: `10` = SOLD 🔴

**Row 3 Detail (showing sold seat):**

| Position | **Seat 1** | Seat 2 | Seat 3 | Seat 4 | Seat 5 |
|----------|------------|--------|--------|--------|--------|
| Index    | **10**     | 11     | 12     | 13     | 14     |
| Offset   | **20**     | 22     | 24     | 26     | 28     |
| Value    | **10**     | 00     | 00     | 00     | 00     |
| Status   | **🔴**     | 🟢     | 🟢     | 🟢     | 🟢     |

All other rows (1, 4, 5) remain `00` (AVAILABLE 🟢)

**Seat ID Format:**

```text
{row}-{seat_num}

Examples:
- 1-1  (Row 1, Seat 1)
- 2-2  (Row 2, Seat 2)
- 5-5  (Row 5, Seat 5)
```

---

## Seat Finding Algorithm

### Lua Script (`find_consecutive_seats.lua`)

**Strategy:**

```lua
-- Priority 1: Find N consecutive seats
for each row:
    seat_statuses = BITFIELD GET u2 ...  -- Batch read entire row

    if found N consecutive:
        return seats  -- SUCCESS

-- Priority 2: Smart fallback (any available seats)
if consecutive_blocks exist:
    return largest blocks  -- e.g., [3 seats] + [2 seats] or [1]+[1]+[1]

return nil  -- Fail (no seats available)
```

---

## Atomic Reservation Execution

### Pipeline Flow

```text
Request → Idempotency Check → Find/Verify → MULTI/EXEC Pipeline → Result
```

### Pipeline Commands (3 seats in 2 rows)

```python
pipe = client.pipeline(transaction=True)

# [0-2] Reserve seats
pipe.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 1)

# [3] Update subsection counter
pipe.decrby(f'seats_avail:{event_id}:{section_id}', 3)

# [4-5] Update row counters
pipe.decrby(f'seats_avail_row:{event_id}:{section_id}:{row}', count)

# [6-9] Update JSON stats
pipe.execute_command('JSON.NUMINCRBY', event_state_key, '$.subsection.available', -3)
pipe.execute_command('JSON.NUMINCRBY', event_state_key, '$.subsection.reserved', 3)
pipe.execute_command('JSON.NUMINCRBY', event_state_key, '$.event_stats.available', -3)
pipe.execute_command('JSON.NUMINCRBY', event_state_key, '$.event_stats.reserved', 3)

# [10] Read updated stats
pipe.execute_command('JSON.GET', event_state_key, '$')

# [11] Save booking metadata
pipe.hset(f'booking:{booking_id}', mapping={...})

results = await pipe.execute()  # 1 round-trip for all
```

**Result Index:** `event_state_idx = num_seats + 1 + num_rows + 4`

---

## State Transitions

### Seat Status (Kvrocks)

```text
AVAILABLE (00) ↔ RESERVED (01)

reserve_seats_atomic(): AVAILABLE → RESERVED
release_seats():        RESERVED → AVAILABLE
```

> **Note**: SOLD 狀態由 PostgreSQL ticket.status 管理，Kvrocks 不追蹤付款後的狀態變更。

### Reservation Workflow

```text
REQUEST → IDEMPOTENCY CHECK
  ├─ Exists → Return cached
  └─ Not exists → FIND SEATS
      ├─ Not found → RESERVE_FAILED
      └─ Found → EXECUTE PIPELINE → SUCCESS
```

---

## Consistency Guarantees

### 1. Redis Atomicity

Each command (BITFIELD, JSON.NUMINCRBY, DECRBY, HSET) is atomic.

### 2. MULTI/EXEC Pipeline

```python
pipe = client.pipeline(transaction=True)  # Isolation + Atomicity
```

All commands succeed or fail together.

### 3. Kafka Sequential Processing

```text
Same booking_id → Same partition → Sequential processing
```

### 4. Idempotency

```python
existing = await client.hgetall(f'booking:{booking_id}')
if existing:
    return cached_result  # No re-execution
```

---

## Error Handling

### Seat Unavailable

```python
if seat_status != 0:
    return {'error': f'Seat {seat_id} is already {status}'}
```

### No Available Seats

```lua
if #consecutive_blocks == 0:
    return nil  -- No seats available at all
```

```python
if not result:
    return {'error': f'No {quantity} seats available'}
```

### Pipeline Failure

```python
try:
    results = await pipe.execute()
except Exception as e:
    await status_manager.save_reservation_failure(booking_id, str(e))
    raise
```

Kafka retries, idempotency prevents duplicates.

---

## Key Patterns

| Pattern | Example | Type | Purpose |
|---------|---------|------|---------|
| `seats_bf:{event_id}:{section_id}` | `seats_bf:123:A-1` | Bitfield | Seat status |
| `event_state:{event_id}` | `event_state:123` | JSON | Config + stats |
| `seats_avail:{event_id}:{section_id}` | `seats_avail:123:A-1` | Integer | Subsection counter |
| `seats_avail_row:{event_id}:{section_id}:{row}` | `seats_avail_row:123:A-1:5` | Integer | Row counter |
| `booking:{booking_id}` | `booking:01JDB...` | Hash | Booking metadata |
| `event_sellout_timer:{event_id}` | `event_sellout_timer:123` | Hash | Sellout metrics |

---

## Implementation Files

- **Lua:** `src/platform/state/lua_scripts/find_consecutive_seats.lua`
- **Executor:** `src/service/reservation/driven_adapter/reservation_helper/atomic_reservation_executor.py`
- **Handler:** `src/service/reservation/driven_adapter/seat_state_command_handler_impl.py`
- **Finder:** `src/service/reservation/driven_adapter/reservation_helper/seat_finder.py`

---

## References

- [Kvrocks Documentation](https://kvrocks.apache.org/)
- [Redis Bitfields](https://redis.io/commands/bitfield/)
- [RedisJSON Commands](https://redis.io/docs/data-types/json/)
- [Lua Scripting](https://redis.io/docs/interact/programmability/eval-intro/)
