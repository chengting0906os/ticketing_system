# Release Workflow Specification

## 1. Overview

This document describes the atomicity mechanism of seat release.

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
SeatReleaseUseCase.execute_batch(request)
    │
    ├── [Step 1] Fetch Booking from DB
    │       ├── booking_command_repo.get_by_id()
    │       └── Get section, subsection, seat_positions, buyer_id
    │
    ├── [Step 2] Idempotency Check
    │       ├── status = CANCELLED → skip to Step 4 (idempotent retry, ensure Kvrocks + SSE complete)
    │       ├── status = PENDING_PAYMENT → continue Step 3 (normal flow)
    │       └── Other status → return error (release not allowed)
    │
    ├── [Step 3] PostgreSQL Write (CTE Atomic Update)
    │       └── update_status_to_cancelled_and_release_tickets()
    │               ├── CTE: UPDATE ticket SET status = 'available'
    │               ├── CTE: UPDATE booking SET status = 'cancelled'
    │               └── [TRIGGER] ticket_status_change_trigger auto-fires:
    │                       ├── UPDATE event.stats (JSONB) → differential +/- update
    │                       └── UPDATE subsection_stats → section statistics
    │
    ├── [Step 4] Fetch Config (Kvrocks)
    │       └── seating_config_handler.get_config() → get cols
    │
    ├── [Step 5] Set Seats (Kvrocks Pipeline)
    │       └── update_seat_map_release()
    │               ├── pipe = client.pipeline(transaction=True)
    │               ├── Commands 1~N: BITFIELD bf_key SET u1 seat_index 0 (1→0)
    │               └── await pipe.execute()
    │
    ├── [Step 6] SSE Broadcast
    │       ├── schedule_stats_broadcast() → broadcast statistics
    │       └── publish_booking_update() → real-time user notification (status=CANCELLED)
    │
    └── Return ReleaseSeatsBatchResult
```

---

## 4. Key Differences from Reservation

| Aspect             | Reservation                | Release               |
| ------------------ | -------------------------- | --------------------- |
| Kvrocks Operation  | BITFIELD SET 0→1           | BITFIELD SET 1→0      |
| PostgreSQL booking | INSERT (PENDING_PAYMENT)   | UPDATE to CANCELLED   |
| PostgreSQL tickets | UPDATE to RESERVED         | UPDATE to AVAILABLE   |
| Idempotency Check  | PENDING_PAYMENT → continue | CANCELLED → continue  |

---

## 5. Implementation References

- [seat_release_use_case.py](../../src/service/reservation/app/command/seat_release_use_case.py)
- [atomic_release_executor.py](../../src/service/reservation/driven_adapter/state/reservation_helper/atomic_release_executor.py)
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py)
