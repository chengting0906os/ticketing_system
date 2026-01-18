# Reservation Workflow Specification

## 1. Overview

本文件描述座位預訂的原子性機制。

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
SeatReservationUseCase.reserve_seats(request)
    │
    ├── [Step 1] Validate Request
    │       ├── MANUAL: 檢查 seat_positions 存在且 <= 4
    │       └── BEST_AVAILABLE: 檢查 quantity 存在且 <= 4
    │
    ├── [Step 2] Idempotency Check（冪等檢查 - PostgreSQL）
    │       ├── 查詢 booking 表: SELECT * FROM booking WHERE id = {booking_id}
    │       ├── 如果 status = FAILED → 返回錯誤
    │       └── 如果 status = PENDING_PAYMENT → 跳到 Step 6（確保 Kvrocks + SSE 完成）
    │
    ├── [Step 3] Fetch Config（Kvrocks）
    │       └── seating_config_handler.get_config() → 取得 rows, cols, price
    │
    ├── [Step 4] Find Seats（Kvrocks）
    │       │
    │       ├── [BEST_AVAILABLE] find_best_available_seats.lua:
    │       │       ├── BITFIELD GET u1 批次讀取整行座位狀態
    │       │       ├── Priority 1: 尋找 N 個連續可用座位
    │       │       ├── Priority 2: 找不到連續 → 用最大連續區塊組合（可能分散）
    │       │       └── 返回 seats[]
    │       │
    │       └── [MANUAL] verify_manual_seats.lua:
    │               ├── BITFIELD GET u1 批次讀取指定座位狀態
    │               ├── 驗證所有座位 status == 0 (AVAILABLE)
    │               └── 返回 seats[]
    │
    ├── [Step 5] PostgreSQL Write（CTE 原子更新）
    │       └── create_booking_and_update_tickets_to_reserved()
    │               ├── CTE: INSERT booking (status=PENDING_PAYMENT)
    │               ├── CTE: UPDATE ticket SET status = 'reserved'
    │               └── [TRIGGER] ticket_status_change_trigger 自動觸發：
    │                       ├── UPDATE event.stats (JSONB) → differential +/- 更新
    │                       └── UPDATE subsection_stats → 區域統計
    │
    ├── [Step 6] Set Seats（Kvrocks）
    │       ├── 命令 1~N: BITFIELD SET u1 seat_index 1（座位狀態 0→1）
    │       └── pipe.execute()
    │
    ├── [Step 7] SSE 廣播
    │       ├── schedule_stats_broadcast() → 廣播統計
    │       └── publish_booking_update() → 即時通知用戶
    │
    └── 返回 ReservationResult
```

---

## 4. Implementation References

- [seat_reservation_use_case.py](../../src/service/reservation/app/command/seat_reservation_use_case.py) - Use Case
- [atomic_reservation_executor.py](../../src/service/reservation/driven_adapter/state/reservation_helper/atomic_reservation_executor.py) - Kvrocks 原子操作
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py) - PostgreSQL 寫入
- [find_best_available_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/find_best_available_seats.lua) - Lua Script
- [verify_manual_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/verify_manual_seats.lua) - Lua Script
- [update_event_stats.sql](../../src/platform/database/trigger/update_event_stats.sql) - PostgreSQL Trigger
