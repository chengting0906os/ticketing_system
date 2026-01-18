# Release Workflow Specification

## 1. Overview

本文件描述座位釋放的原子性機制。

---

## 2. Same Topic + Same Partition Design

- Reserve 和 Release 使用**同一個 Kafka Topic** (`event-id-{event_id}______ticket-command-request______...`)
- 同一區域發到**同一 Partition**。

**Partition 計算**：
```python
section_index = ord(section.upper()) - ord('A')  # A=0, B=1, ...
global_index = section_index * SUBSECTIONS_PER_SECTION + (subsection - 1)
partition = global_index % KAFKA_TOTAL_PARTITIONS
```

**Race Condition Protection**：
- 同一 `section-subsection` → 同一 partition → 順序處理
- **無需 distributed lock** - partition ordering 保證同一區域的訂單依序處理
- 避免 Race Condition：Release 一定在對應的 Reserve 之後處理

---

## 3. PostgreSQL-First Flow (Current Implementation)

```
SeatReleaseUseCase.execute_batch(request)
    │
    ├── [Step 1] Fetch Booking from DB
    │       ├── booking_command_repo.get_by_id()
    │       └── 取得 section, subsection, seat_positions, buyer_id
    │
    ├── [Step 2] Idempotency Check（冪等檢查）
    │       ├── status = CANCELLED → 跳到 Step 4（冪等重試，確保 Kvrocks + SSE 完成）
    │       ├── status = PENDING_PAYMENT → 繼續 Step 3（正常流程）
    │       └── 其他狀態 → 返回錯誤（不允許釋放）
    │
    ├── [Step 3] PostgreSQL Write（CTE 原子更新）
    │       └── update_status_to_cancelled_and_release_tickets()
    │               ├── CTE: UPDATE ticket SET status = 'available'
    │               ├── CTE: UPDATE booking SET status = 'cancelled'
    │               └── [TRIGGER] ticket_status_change_trigger 自動觸發：
    │                       ├── UPDATE event.stats (JSONB) → differential +/- 更新
    │                       └── UPDATE subsection_stats → 區域統計
    │
    ├── [Step 4] Fetch Config（Kvrocks）
    │       └── seating_config_handler.get_config() → 取得 cols
    │
    ├── [Step 5] Set Seats（Kvrocks Pipeline）
    │       └── update_seat_map_release()
    │               ├── pipe = client.pipeline(transaction=True)
    │               ├── 命令 1~N: BITFIELD bf_key SET u1 seat_index 0（1→0）
    │               └── await pipe.execute()
    │
    ├── [Step 6] SSE 廣播
    │       ├── schedule_stats_broadcast() → 廣播統計
    │       └── publish_booking_update() → 即時通知用戶 (status=CANCELLED)
    │
    └── 返回 ReleaseSeatsBatchResult
```

---

## 4. Key Differences from Reservation

| 面向               | Reservation                | Release               |
| ------------------ | -------------------------- | --------------------- |
| Kvrocks 操作       | BITFIELD SET 0→1           | BITFIELD SET 1→0      |
| PostgreSQL booking | INSERT (PENDING_PAYMENT)   | UPDATE to CANCELLED   |
| PostgreSQL tickets | UPDATE to RESERVED         | UPDATE to AVAILABLE   |
| Idempotency 檢查   | PENDING_PAYMENT → continue | CANCELLED → continue  |

---

## 5. Implementation References

- [seat_release_use_case.py](../../src/service/reservation/app/command/seat_release_use_case.py) - Use Case
- [atomic_release_executor.py](../../src/service/reservation/driven_adapter/state/reservation_helper/atomic_release_executor.py) - Kvrocks 原子操作
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py) - PostgreSQL 寫入
