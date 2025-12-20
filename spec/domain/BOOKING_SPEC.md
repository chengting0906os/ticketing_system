# Booking - PRD

## 1. Overview

Booking 模組負責管理購票預訂的建立、查詢、付款與取消流程。買家可以選擇手動選位或最佳可用座位模式進行預訂，系統透過 Kafka 事件驅動架構與 Reservation Service 協作完成座位鎖定，並透過 SSE 即時推送預訂狀態更新。

---

## 2. Business Rules

1. **預訂數量限制**: 每筆預訂最少 1 張，最多 4 張票
2. **選位模式**:
   - `manual`: 手動選位，需提供 seat_positions，數量需與 quantity 一致
   - `best_available`: 系統自動選擇最佳可用座位，seat_positions 須為空陣列
3. **座位格式**: seat_positions 格式為 `"row-seat"`（如 `"1-1"`, `"2-3"`）
4. **Fail Fast 原則**: 建立預訂前先檢查座位可用性，不足則立即回傳錯誤
5. **狀態轉換規則**:
   - 只有 `PROCESSING` 和 `PENDING_PAYMENT` 狀態可以取消
   - 只有 `PENDING_PAYMENT` 狀態可以付款
   - `PROCESSING` 狀態付款回傳 400 "Cannot pay booking in processing state"
   - `COMPLETED`、`CANCELLED`、`FAILED` 為終態，不可再變更
   - 終態嘗試付款或取消回傳 400 "Booking already in terminal state"
6. **無 Timeout**: PENDING_PAYMENT 狀態無時間限制，直到買家付款或取消
7. **權限控制**:
   - 只有預訂的買家可以取消或付款
   - 賣家可以查看其活動的所有預訂
   - 買家只能查看自己的預訂
8. **事件驅動**: 預訂建立/付款/取消皆透過 Kafka 事件通知 Reservation Service 更新座位狀態

---

## 3. User Story

- 作為 Buyer，我需要選擇座位並建立預訂，以便鎖定想要的座位
- 作為 Buyer，我需要使用最佳可用座位功能，以便快速完成預訂
- 作為 Buyer，我需要查看我的預訂詳情，以便確認座位資訊
- 作為 Buyer，我需要取消未付款的預訂，以便釋放座位給其他人
- 作為 Buyer，我需要完成預訂付款，以便確認購票成功
- 作為 Buyer，我需要即時接收預訂狀態更新，以便知道座位是否預訂成功
- 作為 Seller，我需要查看活動的所有預訂，以便管理銷售狀況

---

## 4. Acceptance

### Booking Creation

- [x] Buyer 可以手動選擇 1-4 個座位建立預訂
- [x] Buyer 可以使用最佳可用模式建立預訂
- [x] 手動選位時 seat_positions 數量需與 quantity 一致
- [x] 最佳可用模式時 seat_positions 必須為空陣列
- [x] 預訂數量超過 4 張回傳 400
- [x] 座位不足時立即回傳 400（Fail Fast）
- [x] 預訂建立後狀態為 PROCESSING
- [x] 預訂建立後發送 BookingCreatedDomainEvent

### Booking Payment

- [x] Buyer 可以對 PENDING_PAYMENT 狀態的預訂付款
- [x] 付款成功後狀態變更為 COMPLETED
- [x] 付款成功後關聯的票券狀態變更為 SOLD
- [x] 已付款的預訂無法再次付款
- [x] 已取消的預訂無法付款
- [x] PROCESSING 狀態的預訂無法付款（回傳 400）
- [x] FAILED 狀態的預訂無法付款（回傳 400）
- [x] 非預訂擁有者無法付款

### Booking Cancellation

- [x] Buyer 可以取消 PROCESSING 或 PENDING_PAYMENT 狀態的預訂
- [x] 取消後狀態變更為 CANCELLED
- [x] 取消後座位釋放回可用狀態
- [x] 已完成付款的預訂無法取消
- [x] 已取消的預訂無法再次取消
- [x] FAILED 狀態的預訂無法取消（回傳 400）
- [x] 非預訂擁有者無法取消

### Booking Query

- [x] Buyer 可以查看自己的預訂列表
- [x] Seller 可以查看其活動的所有預訂
- [x] 可依據狀態篩選預訂列表
- [x] 預訂詳情包含活動資訊、買家資訊、座位資訊
- [x] 查詢不存在的預訂回傳 404

### SSE Real-time Updates

- [x] 已驗證用戶可連線 SSE 接收預訂狀態更新
- [x] 未驗證用戶連線 SSE 回傳 401
- [x] 預訂達到終態時自動關閉 SSE 連線

---

## 5. Test Scenarios

### Integration Tests (BDD)

- [booking_creation_integration_test.feature](../../test/service/ticketing/booking/booking_creation_integration_test.feature) - 預訂建立
- [booking_payment_integration_test.feature](../../test/service/ticketing/booking/booking_payment_integration_test.feature) - 預訂付款
- [booking_cancellation_integration_test.feature](../../test/service/ticketing/booking/booking_cancellation_integration_test.feature) - 預訂取消
- [booking_list_integration_test.feature](../../test/service/ticketing/booking/booking_list_integration_test.feature) - 預訂列表
- [booking_sse_integration_test.feature](../../test/service/ticketing/booking/booking_sse_integration_test.feature) - SSE 即時更新

### Unit Tests

- [create_booking_use_case_unit_test.py](../../test/service/ticketing/booking/create_booking_use_case_unit_test.py) - 建立預訂 Use Case
- [update_booking_to_cancelled_use_case_unit_test.py](../../test/service/ticketing/booking/update_booking_to_cancelled_use_case_unit_test.py) - 取消預訂 Use Case

---

## 6. Technical Specification

### 6.1 API Endpoints

| Method | Endpoint                            | Description            | Permission    | Success | Error         |
| ------ | ----------------------------------- | ---------------------- | ------------- | ------- | ------------- |
| POST   | `/api/booking`                      | 建立預訂               | Buyer         | 201     | 400, 401      |
| GET    | `/api/booking/{booking_id}`         | 取得預訂詳情           | Authenticated | 200     | 401, 404      |
| GET    | `/api/booking/my_booking`           | 列出我的預訂           | Authenticated | 200     | 401           |
| PATCH  | `/api/booking/{booking_id}`         | 取消預訂               | Buyer         | 200     | 400, 401, 404 |
| POST   | `/api/booking/{booking_id}/pay`     | 預訂付款               | Buyer         | 200     | 400, 401, 404 |
| GET    | `/api/booking/event/{event_id}/sse` | 訂閱預訂狀態更新 (SSE) | Authenticated | 200     | 401           |

### 6.2 Model

#### BookingModel

| Field                 | Type      | Description                                                       |
| --------------------- | --------- | ----------------------------------------------------------------- |
| `id`                  | UUID      | Primary key (UUID7)                                               |
| `buyer_id`            | int       | 買家 ID (indexed)                                                 |
| `event_id`            | int       | 活動 ID (indexed)                                                 |
| `section`             | str       | 區域                                                              |
| `subsection`          | int       | 子區域                                                            |
| `seat_positions`      | List[str] | 座位清單 (nullable), 格式: `"{row}-{seat}"` e.g. `["1-1", "1-2"]` |
| `quantity`            | int       | 數量 (default=0)                                                  |
| `total_price`         | int       | 總價                                                              |
| `status`              | str       | 預訂狀態 (default='processing')                                   |
| `seat_selection_mode` | str       | 選位模式                                                          |
| `created_at`          | datetime  | 建立時間 (auto)                                                   |
| `updated_at`          | datetime  | 更新時間 (auto)                                                   |
| `paid_at`             | datetime  | 付款時間 (nullable)                                               |

#### BookingStatus Enum

| Value           | Description                          |
| --------------- | ------------------------------------ |
| PROCESSING      | 處理中（初始狀態，等待座位預訂確認） |
| PENDING_PAYMENT | 待付款（座位已預訂成功）             |
| COMPLETED       | 已完成（付款成功）                   |
| CANCELLED       | 已取消                               |
| FAILED          | 預訂失敗（座位預訂失敗）             |

#### Status Transition Diagram

```
                    ┌──────────────┐
                    │  PROCESSING  │
                    └──────┬───────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────┐   ┌───────────────┐   ┌────────┐
    │  FAILED  │   │PENDING_PAYMENT│   │CANCELLED│
    └──────────┘   └───────┬───────┘   └────────┘
                           │                ▲
                    ┌──────┴──────┐         │
                    │             │         │
                    ▼             └─────────┘
             ┌───────────┐
             │ COMPLETED │
             └───────────┘
```

### 6.3 Request/Response Schema

- [booking_schema.py](../../src/service/ticketing/driving_adapter/schema/booking_schema.py) - Request/Response schemas

### 6.4 Domain Events

| Event                     | Trigger  | Consumer            | Action                     |
| ------------------------- | -------- | ------------------- | -------------------------- |
| BookingCreatedDomainEvent | 預訂建立 | Reservation Service | 在 Kvrocks 預訂座位        |
| BookingPaidEvent          | 付款完成 | Reservation Service | 在 Kvrocks 確認座位為 SOLD |
| BookingCancelledEvent     | 預訂取消 | Reservation Service | 在 Kvrocks 釋放座位        |

### 6.5 SSE Architecture

```
Browser ◄── SSE ── Controller ── subscribe ──► Kvrocks Pub/Sub
                                                     ▲
Reservation Service ─────── publish ─────────────────┘
```

**Flow:**

1. SSE 客戶端連線時，訂閱 Kvrocks pub/sub channel `booking:status:{user_id}:{event_id}`
2. Reservation Service 處理座位預訂後，透過 `BookingEventBroadcaster` 發布狀態更新
3. SSE endpoint 收到訂閱訊息後，推送 `status_update` 事件給客戶端
4. 當預訂達到終態（completed/failed/cancelled）時，自動關閉 SSE 連線

### 6.6 Implementation

#### Core Domain

- [booking_entity.py](../../src/service/ticketing/domain/entity/booking_entity.py) - Booking Entity
- [booking_domain_event.py](../../src/service/ticketing/domain/domain_event/booking_domain_event.py) - Domain Events

#### HTTP Controller

- [booking_controller.py](../../src/service/ticketing/driving_adapter/http_controller/booking_controller.py) - REST & SSE endpoints
- [booking_schema.py](../../src/service/ticketing/driving_adapter/schema/booking_schema.py) - Request/Response schemas

#### Use Cases (Command)

- [create_booking_use_case.py](../../src/service/ticketing/app/command/create_booking_use_case.py) - 建立預訂
- [update_booking_status_to_cancelled_use_case.py](../../src/service/ticketing/app/command/update_booking_status_to_cancelled_use_case.py) - 取消預訂
- [mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case.py](../../src/service/ticketing/app/command/mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case.py) - 付款

#### Use Cases (Query)

- [get_booking_use_case.py](../../src/service/ticketing/app/query/get_booking_use_case.py) - 查詢預訂詳情
- [list_bookings_use_case.py](../../src/service/ticketing/app/query/list_bookings_use_case.py) - 列出預訂

#### Repository

- [booking_command_repo_impl.py](../../src/service/ticketing/driven_adapter/repo/booking_command_repo_impl.py) - Command Repository
- [booking_query_repo_impl.py](../../src/service/ticketing/driven_adapter/repo/booking_query_repo_impl.py) - Query Repository
