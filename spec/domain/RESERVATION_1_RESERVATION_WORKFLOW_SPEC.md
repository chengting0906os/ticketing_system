# Reservation Workflow Specification

## 1. Overview

This document describes the atomicity mechanism of seat reservation.

---

## 2. Same Topic + Same Partition Design

- Reserve and Release use **the same Kafka Topic** (`event-id-{event_id}______ticket-command-request______...`)
- Same section goes to **same Partition**.

**Partition Calculation**:
```python
section_index = ord(section.upper()) - ord('A')  # A=0, B=1, ...
global_index = section_index * SUBSECTIONS_PER_SECTION + (subsection - 1)
partition = global_index % KAFKA_TOTAL_PARTITIONS
```

**Race Condition Protection**:
- Same `section-subsection` → same partition → sequential processing
- **No distributed lock needed** - partition ordering guarantees orders in same section are processed sequentially
- Avoid Race Condition: Release is always processed after corresponding Reserve

---

## 3. PostgreSQL-First Flow (Current Implementation)

```
SeatReservationUseCase.reserve_seats(request)
    │
    ├── [Step 1] Validate Request
    │       ├── MANUAL: Check seat_positions exists and <= 4
    │       └── BEST_AVAILABLE: Check quantity exists and <= 4
    │
    ├── [Step 2] Idempotency Check (PostgreSQL)
    │       ├── Query booking table: SELECT * FROM booking WHERE id = {booking_id}
    │       ├── If status = FAILED → return error
    │       └── If status = PENDING_PAYMENT → skip to Step 6 (ensure Kvrocks + SSE complete)
    │
    ├── [Step 3] Fetch Config (Kvrocks)
    │       └── seating_config_handler.get_config() → get rows, cols, price
    │
    ├── [Step 4] Find Seats (Kvrocks)
    │       │
    │       ├── [BEST_AVAILABLE] find_best_available_seats.lua:
    │       │       ├── BITFIELD GET u1 batch read entire row seat status
    │       │       ├── Priority 1: Find N consecutive available seats
    │       │       ├── Priority 2: Not found → use largest consecutive block combination (may be scattered)
    │       │       └── Return seats[]
    │       │
    │       └── [MANUAL] verify_manual_seats.lua:
    │               ├── BITFIELD GET u1 batch read specified seat status
    │               ├── Verify all seats status == 0 (AVAILABLE)
    │               └── Return seats[]
    │
    ├── [Step 5] PostgreSQL Write (CTE Atomic Update)
    │       └── create_booking_and_update_tickets_to_reserved()
    │               ├── CTE: INSERT booking (status=PENDING_PAYMENT)
    │               ├── CTE: UPDATE ticket SET status = 'reserved'
    │               └── [TRIGGER] ticket_status_change_trigger auto-fires:
    │                       ├── UPDATE event.stats (JSONB) → differential +/- update
    │                       └── UPDATE subsection_stats → section statistics
    │
    ├── [Step 6] Set Seats (Kvrocks)
    │       ├── Commands 1~N: BITFIELD SET u1 seat_index 1 (seat status 0→1)
    │       └── pipe.execute()
    │
    ├── [Step 7] SSE Broadcast
    │       ├── schedule_stats_broadcast() → broadcast statistics
    │       └── publish_booking_update() → real-time user notification
    │
    └── Return ReservationResult
```

---

## 4. Implementation References

- [seat_reservation_use_case.py](../../src/service/reservation/app/command/seat_reservation_use_case.py)
- [atomic_reservation_executor.py](../../src/service/reservation/driven_adapter/state/reservation_helper/atomic_reservation_executor.py)
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py)
- [find_best_available_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/find_best_available_seats.lua)
- [verify_manual_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/verify_manual_seats.lua)
- [update_event_stats.sql](../../src/platform/database/trigger/update_event_stats.sql)
