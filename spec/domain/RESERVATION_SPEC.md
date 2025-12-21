# Seat Reservation - PRD

## 1. Overview

Seat Reservation 模組負責管理座位的狀態變更，包括預訂（Reserve）與釋放（Release）。此服務透過 Kafka 接收來自 Ticketing Service 的事件，並操作 Kvrocks 來管理座位狀態，同時將結果寫入 PostgreSQL。

> **Note**: Kvrocks 只追蹤 AVAILABLE/RESERVED 兩種狀態。PostgreSQL 是 SOLD/COMPLETED 狀態的 source of truth。

---

## 2. Business Rules

1. **座位狀態**: Kvrocks 追蹤兩種狀態 - `AVAILABLE`（可用）、`RESERVED`（已預訂）。SOLD 狀態由 PostgreSQL 管理。
2. **原子性操作**: 所有座位操作皆使用 Lua Script 確保原子性
3. **選位模式**:
   - `manual`: 手動選位，需提供指定的座位 ID
   - `best_available`: 系統自動選擇最佳可用連續座位
4. **預訂數量限制**: 每次預訂最多 4 個座位
5. **冪等性**: 使用 booking_id 確保重複訊息不會重複處理
6. **連續座位優先**: best_available 模式優先選擇同一排的連續座位
7. **失敗處理**: 預訂失敗時，建立 FAILED 狀態的 booking 並透過 SSE 通知用戶
8. **即時廣播**: 座位狀態變更後透過 Pub/Sub 推送給 SSE 客戶端

---

## 3. User Story

- 作為 Reservation Service，我需要接收預訂請求並原子性地鎖定座位，以確保不會超賣
- 作為 Reservation Service，我需要在預訂成功後寫入 PostgreSQL，以確保資料一致性
- 作為 Reservation Service，我需要接收取消請求並釋放座位，讓其他用戶可以購買

---

## 4. Acceptance

### Seat Reservation

- [x] 手動選位模式可成功預訂指定座位
- [x] 最佳可用模式可自動選擇連續座位
- [x] 預訂已被預訂的座位回傳失敗
- [x] 部分座位不可用時整筆預訂失敗（原子性）
- [x] 預訂成功後座位狀態變為 RESERVED
- [x] 預訂成功後寫入 PostgreSQL（booking + tickets）
- [x] 預訂失敗時建立 FAILED 狀態的 booking
- [x] 預訂完成後透過 Pub/Sub 發送 SSE 通知
- [x] 超過 4 個座位的預訂請求被拒絕

### Seat Release

- [x] 可批次釋放多個座位
- [x] 釋放成功後座位狀態變為 AVAILABLE
- [x] 支援部分成功（部分座位釋放成功，部分失敗）

### Best Available Algorithm

- [x] 優先選擇同一排的連續座位
- [x] 若同一排無足夠連續座位，嘗試下一排
- [x] 無連續座位時，選擇分散的可用座位

---

## 5. Test Scenarios

### Integration Tests

- [reserve_seats_atomic_integration_test.py](../../test/service/reservation/reserve_seats_atomic_integration_test.py) - 座位預訂原子操作

### Unit Tests

- [seat_reservation_use_case_unit_test.py](../../test/service/reservation/seat_reservation_use_case_unit_test.py) - 預訂 Use Case
- [seat_finder_unit_test.py](../../test/service/reservation/seat_finder_unit_test.py) - 座位搜尋演算法
- [seat_state_command_handler_unit_test.py](../../test/service/reservation/seat_state_command_handler_unit_test.py) - 狀態處理器
- [atomic_reservation_executor_unit_test.py](../../test/service/reservation/atomic_reservation_executor_unit_test.py) - 原子預訂執行器

---

## 6. Technical Specification

### 6.1 MQ Topics (Input)

| Topic Pattern | Description | Producer | Message Type |
| ------------- | ----------- | -------- | ------------ |
| `event-id-{id}______reserve-seats-request______booking___to___reservation` | 座位預訂請求 | Ticketing Service | BookingCreatedDomainEvent |
| `event-id-{id}______release-ticket-status-to-available-in-kvrocks______ticketing___to___reservation` | 座位釋放請求 | Ticketing Service | BookingCancelledEvent |

### 6.2 Seat Status (Kvrocks)

| Status | Value | Description |
| ------ | ----- | ----------- |
| AVAILABLE | 0 | 可預訂 |
| RESERVED | 1 | 已預訂（待付款） |

> **Note**: SOLD 狀態由 PostgreSQL ticket.status 管理，Kvrocks 不追蹤此狀態。

### 6.3 Request/Result DTOs

#### ReservationRequest

| Field | Type | Description |
| ----- | ---- | ----------- |
| `booking_id` | str | 預訂 ID (UUID7) |
| `buyer_id` | int | 買家 ID |
| `event_id` | int | 活動 ID |
| `selection_mode` | str | 選位模式 (manual/best_available) |
| `section_filter` | str | 區域 |
| `subsection_filter` | int | 子區域 |
| `quantity` | int | 座位數量 |
| `seat_positions` | List[str] | 座位清單（手動模式用） |
| `config` | SubsectionConfig | 子區域配置 (rows, cols, price) |

#### ReservationResult

| Field | Type | Description |
| ----- | ---- | ----------- |
| `success` | bool | 是否成功 |
| `booking_id` | str | 預訂 ID |
| `reserved_seats` | List[str] | 預訂成功的座位清單 |
| `total_price` | int | 總價 |
| `error_message` | str | 錯誤訊息（失敗時） |
| `event_id` | int | 活動 ID |

#### ReleaseSeatsBatchRequest

| Field | Type | Description |
| ----- | ---- | ----------- |
| `seat_positions` | List[str] | 座位清單，格式: `"{row}-{seat}"` |
| `event_id` | int | 活動 ID |
| `section` | str | 區域 |
| `subsection` | int | 子區域 |

### 6.4 Kvrocks Data Structure

| Key Pattern | Type | Description |
| ----------- | ---- | ----------- |
| `seats_bf:{event_id}:{section}-{subsection}` | BITFIELD | 座位狀態 (1 bit per seat: u1, 0=available, 1=reserved) |
| `seats_config:{event_id}:{section}-{subsection}` | HASH | 子區域配置 (rows, cols, price) |
| `subsection_stats:{event_id}:{section}-{subsection}` | HASH | 統計 (available, reserved) |
| `seat_booking:{event_id}:{section}-{subsection}:{row}-{seat}` | STRING | 座位對應的 booking_id |

### 6.5 Implementation

#### MQ Consumer

- [reservation_mq_consumer.py](../../src/service/reservation/driving_adapter/reservation_mq_consumer.py) - Kafka Consumer
- [start_reservation_consumer.py](../../src/service/reservation/driving_adapter/start_reservation_consumer.py) - Consumer 啟動入口

#### Use Cases (Command)

- [seat_reservation_use_case.py](../../src/service/reservation/app/command/seat_reservation_use_case.py) - 預訂座位
- [seat_release_use_case.py](../../src/service/reservation/app/command/seat_release_use_case.py) - 釋放座位

#### Use Cases (Query)

- [list_all_subsection_status_use_case.py](../../src/service/reservation/app/query/list_all_subsection_status_use_case.py) - 查詢所有子區域狀態

#### Interfaces

- [i_seat_state_command_handler.py](../../src/service/reservation/app/interface/i_seat_state_command_handler.py) - 座位狀態寫入介面
- [i_booking_command_repo.py](../../src/service/reservation/app/interface/i_booking_command_repo.py) - Booking 寫入介面

#### Driven Adapters

- [seat_state_command_handler_impl.py](../../src/service/reservation/driven_adapter/seat_state_command_handler_impl.py) - Kvrocks 座位操作
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py) - PostgreSQL Booking 寫入

#### Reservation Helpers

- [atomic_reservation_executor.py](../../src/service/reservation/driven_adapter/reservation_helper/atomic_reservation_executor.py) - 原子預訂執行器
- [seat_finder.py](../../src/service/reservation/driven_adapter/reservation_helper/seat_finder.py) - 最佳座位搜尋
- [release_executor.py](../../src/service/reservation/driven_adapter/reservation_helper/release_executor.py) - 座位釋放執行器

### 6.6 Architecture Flow

```
Ticketing Service ──Kafka──> Reservation Service ──> Kvrocks + PostgreSQL + Pub/Sub
```

**Flow:**

1. Ticketing Service 發送 BookingCreatedDomainEvent 到 Kafka
2. Reservation Consumer 接收訊息，執行 ReserveSeatsUseCase
3. 使用 Lua Script 原子性地在 Kvrocks 預訂座位
4. 預訂成功後寫入 PostgreSQL（booking + tickets）
5. 透過 Pub/Sub 發送 SSE 通知給前端
6. 取消流程類似，透過 release topic 觸發座位釋放

> **Note**: 付款流程直接由 Ticketing Service 更新 PostgreSQL，不需要通知 Reservation Service 更新 Kvrocks。
