# Event Ticketing - PRD

## 1. Overview

Event Ticketing 模組負責管理活動（Event）與票券（Ticket）的建立、查詢、以及即時座位狀態推送。賣家可以建立活動並自動生成座位票券，買家可以查詢可購買的活動列表，並透過 SSE 即時接收座位狀態更新。

---

## 2. Business Rules

1. **活動建立權限**: 只有 Seller 可以建立活動
2. **票券自動生成**: 建立活動時根據 `seating_config` 自動生成所有座位票券
3. **活動狀態流程**: DRAFT → AVAILABLE → SOLD_OUT / COMPLETED / ENDED
4. **活動列表過濾**:
   - Seller: 可查看自己所有活動（任何狀態）
   - Buyer: 只能查看 `is_active=true` 且 `status=available` 的活動
5. **座位配置格式** (Compact Format):
   ```json
   {
     "rows": 25,
     "cols": 20,
     "sections": [{ "name": "A", "price": 2000, "subsections": 2 }]
   }
   ```
6. **票價驗證**: 票價必須大於等於 0
7. **補償交易**: 若 Kvrocks 初始化失敗，需回滾已建立的 Event 和 Ticket
8. **即時狀態推送**: 使用 Redis Pub/Sub 訂閱模式，當座位狀態變化時即時推送給 SSE 客戶端

---

## 3. User Story

- 作為 Seller，我需要建立活動並自動生成座位票券，以便買家購票
- 作為 Seller，我需要查看自己所有活動，以便管理活動狀態
- 作為 Buyer，我需要查看可購買的活動列表，以便選擇想參加的活動
- 作為 User，我需要查看活動詳情及座位剩餘數量，以便決定購買哪個區域
- 作為 User，我需要即時接收座位狀態更新，以便看到最新的座位可用情況

---

## 4. Acceptance

### Event CRUD

- [x] Seller 可以成功建立活動，並自動生成票券
- [x] 活動建立後，票券數量 = rows × cols × sections × subsections
- [x] Buyer 無法建立活動 (403)
- [x] 活動名稱不可為空 (400)
- [x] 票價不可為負數 (400)
- [x] 無效的 seating_config 回傳 400
- [x] Seller 可查看自己所有活動（含非 available 狀態）
- [x] Buyer 只能看到 is_active=true 且 status=available 的活動
- [x] 查詢單一活動時，回傳即時座位剩餘數量（從 Kvrocks 取得）
- [x] 查詢單一活動時，回傳所有票券資訊
- [x] 查詢不存在的活動回傳 404
- [x] Kvrocks 初始化失敗時，執行補償交易（刪除已建立的資料）

### SSE Real-time Updates

- [x] SSE 連線時立即回傳初始狀態
- [x] 座位狀態變化時透過 Pub/Sub 推送給所有訂閱者
- [x] 多個 SSE 客戶端可同時訂閱同一活動
- [x] SSE 連線非存在活動回傳 404

---

## 5. Test Scenarios

### Integration Tests (BDD)

- [event_creation.feature](../../test/service/ticketing/event_ticketing/event_creation.feature) - 活動建立
- [event_list_validation.feature](../../test/service/ticketing/event_ticketing/event_list_validation.feature) - 活動列表
- [event_get_with_tickets.feature](../../test/service/ticketing/event_ticketing/event_get_with_tickets.feature) - 活動詳情
- [event_subsection_seats_list_integration_test.feature](../../test/service/ticketing/event_ticketing/event_subsection_seats_list_integration_test.feature) - 座位清單
- [event_status_sse_stream_integration_test.feature](../../test/service/ticketing/event_ticketing/event_status_sse_stream_integration_test.feature) - SSE 即時更新

### Unit Tests

- [init_event_and_tickets_use_case_unit_test.py](../../test/service/ticketing/event_ticketing/init_event_and_tickets_use_case_unit_test.py) - Kafka 設置
- [init_seats_handler_unit_test.py](../../test/service/ticketing/event_ticketing/init_seats_handler_unit_test.py) - Kvrocks 初始化
- [real_time_event_state_subscriber_unit_test.py](../../test/service/ticketing/event_ticketing/real_time_event_state_subscriber_unit_test.py) - Pub/Sub 訂閱

---

## 6. Technical Specification

### 6.1 API Endpoints

| Method | Endpoint                                                                     | Description                  | Permission | Success | Error    |
| ------ | ---------------------------------------------------------------------------- | ---------------------------- | ---------- | ------- | -------- |
| POST   | `/api/event`                                                                 | 建立活動                     | Seller     | 201     | 400, 403 |
| GET    | `/api/event`                                                                 | 列出所有可購買活動           | Public     | 200     | -        |
| GET    | `/api/event?seller_id={id}`                                                  | 列出賣家所有活動             | Public     | 200     | -        |
| GET    | `/api/event/{event_id}`                                                      | 取得活動詳情（含座位剩餘）   | Public     | 200     | 404      |
| GET    | `/api/event/{event_id}/all_subsection_status`                                | 取得所有子區域狀態統計       | Public     | 200     | -        |
| GET    | `/api/event/{event_id}/sections/{section}/subsection/{subsection}/seats`     | 取得指定子區域座位清單       | Public     | 200     | 404      |
| GET    | `/api/event/{event_id}/all_subsection_status/sse`                            | 訂閱所有子區域狀態更新 (SSE) | Public     | 200     | 404      |

### 6.2 Model

#### EventModel

| Field            | Type | Description                    |
| ---------------- | ---- | ------------------------------ |
| `id`             | int  | Primary key (auto)             |
| `name`           | str  | 活動名稱                       |
| `description`    | str  | 活動描述                       |
| `seller_id`      | int  | FK to User                     |
| `is_active`      | bool | 是否上架 (default=True)        |
| `status`         | str  | 活動狀態 (default='available') |
| `venue_name`     | str  | 場地名稱                       |
| `seating_config` | JSON | 座位配置                       |

#### TicketModel

| Field         | Type     | Description                    |
| ------------- | -------- | ------------------------------ |
| `id`          | int      | Primary key (auto)             |
| `event_id`    | int      | 活動 ID (indexed)              |
| `section`     | str      | 區域名稱                       |
| `subsection`  | int      | 子區域編號                     |
| `row_number`  | int      | 排號                           |
| `seat_number` | int      | 座位號                         |
| `price`       | int      | 票價                           |
| `status`      | str      | 票券狀態 (default='available') |
| `buyer_id`    | int      | 購買者 ID (nullable, indexed)  |
| `reserved_at` | datetime | 預留時間 (nullable)            |
| `created_at`  | datetime | 建立時間 (auto)                |
| `updated_at`  | datetime | 更新時間 (auto)                |

**Unique Constraint**: `(event_id, section, subsection, row_number, seat_number)`

### 6.3 Request/Response Schema

See [event_schema.py](../../src/service/ticketing/driving_adapter/schema/event_schema.py)

#### SSE Event Format

```
event: initial_status
data: {"event_type": "initial_status", "event_id": 1, "sections": [...], "total_sections": 4}

event: status_update
data: {"event_type": "status_update", "event_id": 1, "sections": [...], "total_sections": 4}
```

### 6.4 SSE Architecture (Pub/Sub Pattern)

1. SSE 客戶端連線時，查詢 Kvrocks 取得初始狀態並推送 `initial_status`
2. 訂閱 Redis Pub/Sub channel `event_state_updates:{event_id}`
3. Reservation Service 更新座位後，透過 `IPubSubHandler.broadcast_event_state()` 發布到 channel
4. SSE endpoint 收到訊息後推送 `status_update` 給客戶端
5. 客戶端斷線時自動清理連線

### 6.5 Implementation

#### Core Domain

- [event_ticketing_aggregate.py](../../src/service/ticketing/domain/aggregate/event_ticketing_aggregate.py) - Aggregate Root

#### HTTP Controller

- [event_ticketing_controller.py](../../src/service/ticketing/driving_adapter/http_controller/event_ticketing_controller.py) - REST & SSE endpoints
- [event_schema.py](../../src/service/ticketing/driving_adapter/schema/event_schema.py) - Request/Response schemas

#### Use Cases

- [create_event_and_tickets_use_case.py](../../src/service/ticketing/app/command/create_event_and_tickets_use_case.py) - 建立活動
- [get_event_use_case.py](../../src/service/ticketing/app/query/get_event_use_case.py) - 查詢活動詳情
- [list_events_use_case.py](../../src/service/ticketing/app/query/list_events_use_case.py) - 列出活動
- [list_all_subsection_status_use_case.py](../../src/service/reservation/app/query/list_all_subsection_status_use_case.py) - 子區域狀態
- [list_section_seats_detail_use_case.py](../../src/service/reservation/app/query/list_section_seats_detail_use_case.py) - 座位清單

#### Pub/Sub Components

- [pubsub_handler_impl.py](../../src/service/shared_kernel/driven_adapter/pubsub_handler_impl.py) - 發布狀態更新 (broadcast_event_state + publish_booking_update)
- [real_time_event_state_subscriber.py](../../src/service/ticketing/driven_adapter/state/real_time_event_state_subscriber.py) - 訂閱狀態更新

#### State Handler

- [init_event_and_tickets_state_handler_impl.py](../../src/service/ticketing/driven_adapter/state/init_event_and_tickets_state_handler_impl.py) - Kvrocks 初始化
- [seat_state_query_handler_impl.py](../../src/service/ticketing/driven_adapter/state/seat_state_query_handler_impl.py) - 座位狀態查詢
