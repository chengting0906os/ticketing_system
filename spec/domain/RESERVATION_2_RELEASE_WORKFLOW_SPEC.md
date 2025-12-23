# Release Workflow Specification

## 1. Overview

本文件描述座位釋放的原子性機制。

---

## 2. PostgreSQL First Flow

```
SeatReleaseUseCase.execute_batch(request)
    │
    ├── [Step 1] Validate Request
    │       └── 檢查 seat_positions 存在
    │
    ├── [Step 2] Idempotency Check（冪等檢查 - PostgreSQL）
    │       ├── 查詢 booking 表: SELECT * FROM booking WHERE id = {booking_id}
    │       ├── 如果 status = CANCELLED → 跳到 Step 4（確保 Kvrocks + SSE 完成）
    │       └── 如果 status != PENDING_PAYMENT → 返回錯誤
    │
    ├── [Step 3] PostgreSQL 寫入（更新狀態）
    │       ├── UPDATE booking SET status = CANCELLED WHERE id = {booking_id}
    │       └── UPDATE tickets SET status = AVAILABLE WHERE booking_id = {booking_id}
    │
    ├── [Step 4] Kvrocks Pipeline 原子執行（更新座位圖）
    │       ├── fetch_release_config() → 取得 cols
    │       ├── _build_seats_to_release() → 計算 seat_index
    │       ├── 命令 1~N: BITFIELD SET u1 seat_index 0（座位狀態 1→0）
    │       └── pipe.execute()
    │
    ├── [Step 5] SSE 廣播
    │       ├── schedule_stats_broadcast() → 節流廣播統計
    │       └── publish_booking_update() → 即時通知用戶
    │
    └── 返回 ReleaseSeatsBatchResult
```

---

## 3. Key Differences from Reservation

| 面向 | Reservation | Release |
|------|-------------|---------|
| Kvrocks 操作 | BITFIELD SET 0→1 | BITFIELD SET 1→0 |
| PostgreSQL booking | INSERT PENDING_PAYMENT | UPDATE to CANCELLED |
| PostgreSQL tickets | UPDATE to RESERVED | UPDATE to AVAILABLE |
| Idempotency 檢查 | PENDING_PAYMENT → continue | CANCELLED → continue |

---

## 4. Implementation References

- [seat_release_use_case.py](../../src/service/reservation/app/command/seat_release_use_case.py) - Use Case
- [atomic_release_executor.py](../../src/service/reservation/driven_adapter/state/reservation_helper/atomic_release_executor.py) - Kvrocks 原子操作
- [seat_state_release_command_handler_impl.py](../../src/service/reservation/driven_adapter/state/seat_state_release_command_handler_impl.py) - Handler
