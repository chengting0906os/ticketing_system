# Reservation Workflow Specification

## 1. Overview

本文件描述座位預訂的原子性機制。

---

## 2. Atomicity Mechanism

```
SeatReservationUseCase.reserve_seats(request)
    │
    ├── [Step 1] Validate Request
    │       ├── MANUAL: 檢查 seat_positions 存在且 <= 4
    │       └── BEST_AVAILABLE: 檢查 quantity 存在且 <= 4
    │
    ├── [Step 2] Kvrocks 原子預訂 (seat_state_handler.reserve_seats_atomic)
    │       │
    │       ├── [2.1] Idempotency Check（冪等檢查）
    │       │       ├── 讀取 booking:{booking_id} metadata
    │       │       ├── 如果 RESERVE_SUCCESS → 返回快取結果，跳過所有操作
    │       │       └── 如果 RESERVE_FAILED → 返回錯誤
    │       │
    │       ├── [2.2] Lua Script 原子執行（讀取 + 驗證）
    │       │       │
    │       │       ├── 說明: Lua 在 Kvrocks 中原子執行，無法被其他命令中斷
    │       │       │
    │       │       ├── [BEST_AVAILABLE] find_consecutive_seats.lua:
    │       │       │       ├── BITFIELD GET u1 批次讀取整行座位狀態
    │       │       │       ├── 尋找 N 個連續可用座位 (status == 0)
    │       │       │       ├── 找到 → 返回 seats[]
    │       │       │       └── 找不到連續 → Fallback 返回分散可用座位
    │       │       │
    │       │       └── [MANUAL] verify_manual_seats.lua:
    │       │               ├── BITFIELD GET u1 批次讀取指定座位狀態
    │       │               ├── 驗證所有座位 status == 0 (AVAILABLE)
    │       │               ├── 任一座位 status == 1 → 拋錯 SEAT_UNAVAILABLE
    │       │               └── 全部可用 → 返回 seats[] + price
    │       │
    │       └── [2.3] Pipeline 原子執行（批次寫入）
    │               ├── 命令 1~N: BITFIELD SET u1 seat_index 1（座位狀態 0→1）
    │               ├── 命令 N+1: JSON.NUMINCRBY $.event_stats.available -N
    │               ├── 命令 N+2: JSON.NUMINCRBY $.event_stats.reserved +N
    │               ├── 命令 N+3: JSON.GET 讀取最新統計
    │               ├── 命令 N+4: HSET booking:{booking_id} status=RESERVE_SUCCESS
    │               └── pipe.execute() → 所有命令作為單一事務執行
    │
    ├── [Step 3] PostgreSQL 寫入 (booking_command_repo)
    │       │
    │       ├── [SUCCESS] create_booking_and_update_tickets_to_reserved()
    │       │       ├── INSERT booking (status=PENDING_PAYMENT)
    │       │       └── UPDATE tickets SET status=RESERVED WHERE seat_position IN (...)
    │       │
    │       └── [FAILURE] create_failed_booking_directly()
    │               └── INSERT booking (status=FAILED)
    │
    ├── [Step 4] SSE 廣播 (pubsub_handler)
    │       ├── schedule_stats_broadcast() → 節流 1s 後廣播統計
    │       └── publish_booking_update() → 即時通知用戶
    │               ├── [SUCCESS] status=PENDING_PAYMENT, tickets=[...]
    │               └── [FAILURE] status=FAILED, error_message=...
    │
    └── 返回 ReservationResult
```

**Race Condition Protection**: Kafka Partition Ordering
- 同一 `section-subsection` 作為 partition key → 同一 partition → 順序處理

---

## 3. Proposed New Flow (PostgreSQL First)

```
SeatReservationUseCase.reserve_seats(request)
    │
    ├── [Step 1] Validate Request
    │       ├── MANUAL: 檢查 seat_positions 存在且 <= 4
    │       └── BEST_AVAILABLE: 檢查 quantity 存在且 <= 4
    │
    ├── [Step 2] Idempotency Check（冪等檢查 - PostgreSQL）
    │       ├── 查詢 booking 表: SELECT * FROM booking WHERE id = {booking_id}
    │       ├── 如果 status = FAILED → 返回錯誤（SSE 通知，不重複建立 booking）
    │       └── 如果 status = PENDING_PAYMENT → 跳到 Step 5（確保 Kvrocks + SSE 完成）
    │
    ├── [Step 3] Lua Script 原子執行（找座位）
    │       │
    │       ├── [BEST_AVAILABLE] find_consecutive_seats.lua:
    │       │       ├── BITFIELD GET u1 批次讀取整行座位狀態
    │       │       ├── 尋找 N 個連續可用座位 (status == 0)
    │       │       └── 返回 seats[]
    │       │
    │       └── [MANUAL] verify_manual_seats.lua:
    │               ├── BITFIELD GET u1 批次讀取指定座位狀態
    │               ├── 驗證所有座位 status == 0 (AVAILABLE)
    │               └── 返回 seats[]
    │
    ├── [Step 4] PostgreSQL 寫入（座位資料）
    │       ├── INSERT booking (status=PENDING_PAYMENT)
    │       └── UPDATE tickets SET status=RESERVED WHERE seat_position IN (...)
    │
    ├── [Step 5] Kvrocks Pipeline 原子執行（更新座位圖）
    │       ├── 命令 1~N: BITFIELD SET u1 seat_index 1（座位狀態 0→1）
    │       ├── 命令 N+1: JSON.NUMINCRBY $.event_stats.available -N
    │       ├── 命令 N+2: JSON.NUMINCRBY $.event_stats.reserved +N
    │       └── pipe.execute()
    │
    ├── [Step 6] SSE 廣播
    │       ├── schedule_stats_broadcast() → 節流廣播統計
    │       └── publish_booking_update() → 即時通知用戶
    │
    └── 返回 ReservationResult
```

---

## 4. Implementation References

- [seat_reservation_use_case.py](../../src/service/reservation/app/command/seat_reservation_use_case.py) - Use Case
- [atomic_reservation_executor.py](../../src/service/reservation/driven_adapter/state/reservation_helper/atomic_reservation_executor.py) - Kvrocks 原子操作
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py) - PostgreSQL 寫入
- [find_consecutive_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/find_consecutive_seats.lua) - Lua Script
- [verify_manual_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/verify_manual_seats.lua) - Lua Script
