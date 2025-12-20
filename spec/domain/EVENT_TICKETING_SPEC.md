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
     "sections": [
       {"name": "A", "price": 2000, "subsections": 2}
     ]
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

#### Event Management

| Method | Endpoint | Description | Permission | Success | Error |
|--------|----------|-------------|------------|---------|-------|
| POST | `/api/event` | 建立活動 | Seller | 201 | 400, 403 |
| GET | `/api/event` | 列出所有可購買活動 | Public | 200 | - |
| GET | `/api/event?seller_id={id}` | 列出賣家所有活動 | Public | 200 | - |
| GET | `/api/event/{event_id}` | 取得活動詳情（含座位剩餘） | Public | 200 | 404 |

#### Seat Status (from Kvrocks)

| Method | Endpoint | Description | Permission | Success | Error |
|--------|----------|-------------|------------|---------|-------|
| GET | `/api/event/{event_id}/all_subsection_status` | 取得所有子區域狀態統計 | Public | 200 | - |
| GET | `/api/event/{event_id}/sections/{section}/subsection/{subsection}/seats` | 取得指定子區域座位清單 | Public | 200 | 404 |

#### SSE Real-time Updates (Pub/Sub Subscribe)

| Method | Endpoint | Description | Permission | Success | Error |
|--------|----------|-------------|------------|---------|-------|
| GET | `/api/event/{event_id}/all_subsection_status/sse` | 訂閱所有子區域狀態更新 | Public | 200 (SSE) | 404 |
| GET | `/api/event/{event_id}/sections/{section}/subsection/{subsection}/seats/sse` | 訂閱指定子區域座位更新 | Public | 200 (SSE) | 404 |

### 6.2 Model

#### Event Entity

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `id` | int | Primary key | Auto-generated |
| `name` | str | 活動名稱 | Not empty |
| `description` | str | 活動描述 | Not empty |
| `seller_id` | int | 賣家 ID | FK to User |
| `venue_name` | str | 場地名稱 | Not empty |
| `seating_config` | Dict | 座位配置 | JSON |
| `is_active` | bool | 是否上架 | default=True |
| `status` | EventStatus | 活動狀態 | Enum |
| `created_at` | datetime | 建立時間 | Auto |
| `updated_at` | datetime | 更新時間 | Auto |

#### Ticket Entity

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `id` | int | Primary key | Auto-generated |
| `event_id` | int | 活動 ID | FK to Event |
| `section` | str | 區域名稱 | e.g., "A" |
| `subsection` | int | 子區域編號 | e.g., 1 |
| `row` | int | 排號 | e.g., 1 |
| `seat` | int | 座位號 | e.g., 1 |
| `price` | int | 票價 | >= 0 |
| `status` | TicketStatus | 票券狀態 | Enum |
| `buyer_id` | int | 購買者 ID | Nullable |
| `seat_identifier` | str | 座位識別碼 | e.g., "A-1-1-1" |

#### EventStatus Enum

| Value | Description |
|-------|-------------|
| DRAFT | 草稿（剛建立，尚未生成票券） |
| AVAILABLE | 可購買 |
| SOLD_OUT | 售罄 |
| COMPLETED | 已完成 |
| ENDED | 已結束 |

#### TicketStatus Enum

| Value | Description |
|-------|-------------|
| AVAILABLE | 可購買 |
| RESERVED | 已預留 |
| SOLD | 已售出 |

### 6.3 Request/Response Schema

#### EventCreateWithTicketConfigRequest

```json
{
  "name": "Rock Concert",
  "description": "Amazing live rock music show",
  "venue_name": "Taipei Arena",
  "seating_config": {
    "rows": 25,
    "cols": 20,
    "sections": [
      {"name": "A", "price": 2000, "subsections": 2},
      {"name": "B", "price": 1500, "subsections": 1}
    ]
  },
  "is_active": true
}
```

#### EventResponse

```json
{
  "id": 1,
  "name": "Rock Concert",
  "description": "Amazing live rock music show",
  "seller_id": 1,
  "venue_name": "Taipei Arena",
  "seating_config": {
    "rows": 25,
    "cols": 20,
    "sections": [
      {
        "name": "A",
        "price": 2000,
        "subsections": [
          {"number": 1, "available": 480, "reserved": 10, "sold": 10, "total": 500},
          {"number": 2, "available": 500, "reserved": 0, "sold": 0, "total": 500}
        ]
      }
    ]
  },
  "is_active": true,
  "status": "available",
  "tickets": [
    {"id": 1, "event_id": 1, "section": "A", "subsection": 1, "row": 1, "seat": 1, "price": 2000, "status": "available", "seat_identifier": "A-1-1-1"}
  ]
}
```

#### SeatResponse (from Kvrocks)

```json
{
  "event_id": 1,
  "section": "A",
  "subsection": 1,
  "row": 1,
  "seat": 1,
  "price": 2000,
  "status": "available",
  "seat_identifier": "A-1-1-1"
}
```

#### SectionStatsResponse

```json
{
  "event_id": 1,
  "section": "A",
  "subsection": 1,
  "total": 500,
  "available": 480,
  "reserved": 15,
  "sold": 5,
  "tickets": [
    {"event_id": 1, "section": "A", "subsection": 1, "row": 1, "seat": 1, "price": 2000, "status": "available", "seat_identifier": "A-1-1-1"}
  ],
  "total_count": 500
}
```

#### SSE Event Format

```
event: initial_status
data: {"event_type": "initial_status", "event_id": 1, "sections": [...], "total_sections": 4}

event: status_update
data: {"event_type": "status_update", "event_id": 1, "sections": [...], "total_sections": 4}
```

### 6.4 SSE Architecture (Pub/Sub Subscribe Pattern)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SSE Subscribe Flow                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────┐                                          ┌─────────────────┐  │
│   │   Browser   │◄─── SSE (initial_status) ───────────────│  event_ticketing │  │
│   │   Client    │◄─── SSE (status_update)  ───────────────│    _controller   │  │
│   └─────────────┘                                          └────────┬────────┘  │
│                                                                      │           │
│                                                              subscribe│           │
│                                                                      ▼           │
│   ┌─────────────┐     publish          ┌──────────────────────────────────────┐ │
│   │ Reservation │────────────────────►│  Redis Pub/Sub                        │ │
│   │   Service   │                      │  Channel: event_state_updates:{id}   │ │
│   └─────────────┘                      └──────────────────────────────────────┘ │
│         │                                                                        │
│         │ reserve_seats                                                          │
│         ▼                                                                        │
│   ┌─────────────┐                                                                │
│   │   Kvrocks   │◄─── query initial status ─────────────────────────────────────┤
│   │ (Seat State)│                                                                │
│   └─────────────┘                                                                │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Flow:**
1. SSE 客戶端連線時，立即查詢 Kvrocks 取得初始狀態並推送 `initial_status` 事件
2. 訂閱 Redis Pub/Sub channel `event_state_updates:{event_id}`
3. 當 Reservation Service 更新座位狀態後，透過 `EventStateBroadcaster` 發布更新到 channel
4. SSE endpoint 收到訂閱訊息後，推送 `status_update` 事件給客戶端
5. 客戶端斷線時自動清理 pub/sub 連線

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
- [event_state_broadcaster_impl.py](../../src/service/reservation/driven_adapter/event_state_broadcaster_impl.py) - 發布狀態更新
- [real_time_event_state_subscriber.py](../../src/service/ticketing/driven_adapter/state/real_time_event_state_subscriber.py) - 訂閱狀態更新

#### State Handler
- [init_event_and_tickets_state_handler_impl.py](../../src/service/ticketing/driven_adapter/state/init_event_and_tickets_state_handler_impl.py) - Kvrocks 初始化
- [seat_state_query_handler_impl.py](../../src/service/ticketing/driven_adapter/state/seat_state_query_handler_impl.py) - 座位狀態查詢
