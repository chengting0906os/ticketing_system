# Distributed Ticketing System
A high-performance event ticketing platform built with Clean Architecture, BDD/TDD principles, and event-driven microservices.

## System Overview
**Capacity**: 50,000 tickets per event
**Architecture**: 3 microservices + RocksDB + Kafka
**Concurrency**: Lock-free seat reservations
**Deployment**: 2 servers with 10 Kafka partitions

## Core Features
- **Real-time seat reservation** with atomic RocksDB operations
- **Event-driven microservices** communication via Kafka
- **Payment timeout handling** with Redis TTL (15 minutes)
- **Live updates** to frontend via Server-Sent Events (SSE)
- **High availability** distributed deployment

## User Stories

### Authentication & User Management
- As a visitor, I can register as a seller
- As a visitor, I can register as a buyer
- As a user, I can login and logout securely

### Seller (Event Organizer)
- As a seller, I can create events with custom seating configurations
- As a seller, I can manage ticket pricing by sections
- As a seller, I can view real-time sales analytics
- As a seller, I can monitor seat reservation status

### Buyer (Ticket Purchaser)
- As a buyer, I can browse available events
- As a buyer, I can select seats in real-time without conflicts
- As a buyer, I can complete payment within 15-minute window
- As a buyer, I can view my booking history and tickets
- As a buyer, I can receive live updates on seat availability


# 票務系統架構圖

## 三微服務架構 + RocksDB 無鎖預訂

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   booking_service   │────▶│   seat_reservation   │────▶│   event_ticketing   │
│    (PostgreSQL)     │     │   (Algorithm Router) │     │ (PostgreSQL+RocksDB)│
│                     │◀────│                      │◀────│                     │
│  📊 Consumer: 1     │     │  📊 Consumer: 1      │     │  📊 Consumer: 2     │
│ event-id-1__        │     │ event-id-1__         │     │ event-id-1__        │
│ booking-service-1   │     │ seat-reservation-    │     │ event-ticketing-    │
│                     │     │ service-1            │     │ service-1           │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
         │                           │                          │
         │                           │                          │
         ▼                           ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Kafka + Quix Streams                            │
│                   Event-Driven + Stateful Stream + Lock-Free                │
│                          🔄 1:1:2 Consumer Architecture                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Topic 和 Partition 策略

### 📡 Topic 命名格式
```
event-id-{event_id}______{action}______{from_service}___to___{to_service}
例如：event-id-123______ticket-reserve-request______booking-service___to___seat-reservation-service
例如：event-id-123______update-booking-status-to-pending-payment______seat-reservation-service___to___booking-service
```

### 🎯 Partition Key 格式
```
event-{event_id}-section-{section}-partition-{partition_number}
例如：event-123-section-A-partition-0
```

### 🗂️ 主要 Topics
- `event-id-{event_id}______ticket-reserve-request______booking-service___to___seat-reservation-service` - 票據預訂請求
- `event-id-{event_id}______update-ticket-status-to-reserved______seat-reservation-service___to___event-ticketing-service` - 更新票據狀態為預訂
- `event-id-{event_id}______update-booking-status-to-pending-payment______seat-reservation-service___to___booking-service` - 更新訂單狀態為待付款
- `event-id-{event_id}______update-booking-status-to-failed______seat-reservation-service___to___booking-service` - 訂單狀態為失敗
- `event-id-{event_id}______update-ticket-status-to-paid______booking-service___to___event-ticketing-service` - 更新票據狀態為已付款
- `event-id-{event_id}______update-ticket-status-to-available______booking-service___to___event-ticketing-service` - 更新票據狀態為可用
- `event-id-{event_id}______release-ticket-to-available-by-rocksdb______event-ticketing-service___to___seat-reservation-service` - 釋放票據到可用狀態
- `event-id-{event_id}______finalize-ticket-to-paid-by-rocksdb______event-ticketing-service___to___seat-reservation-service` - 確認票據為已付款
- `event-id-{event_id}______seat-initialization-command______event-ticketing-service___to___event-ticketing-service` - 座位初始化指令

### ⚡ 區域集中式 Partition 策略
- **A區所有座位** → 固定 partition (例如 partition-0)
- **B區所有座位** → 固定 partition (例如 partition-1)
- **同區域查詢效率極高** → 只需查詢單一 partition
- **原子性保證** → 區域內座位操作在同一 RocksDB instance



## 詳細預訂流程

### 🎫 Step 1: booking service 訂單創建 1 server 1 consumer
**booking_service** 創建訂單:
```
→ booking raw create and status: PROCESSING
→ 發送事件到: event-id-123___:ticket-reserve-request___:seat-reservation-service
→ partition_key: event-123-section-A-partition-0 # booking_service 透過 partition_key 分流到不同 consumer/partition
→ 事件: TicketReservedRequest(**booking_data)
→ return booking detail 200
```

### 🪑 Step 2: seat_reservation service  2 server 2 consumer
**seat_reservation** 
收到 topic event-id-123___:ticket-reserve-request___:seat-reservation-service 

**seat selection service 查詢座位 strategry**
exactly once sequential processing
- best-available
```
讀取座位狀況
連續座位先找同排座位
沒有就 / 2 拆散
直到全部找到座位或選到幾張算幾張
透過 partition_key 原子更新 RocksDB 座位
```
- manual
```
沒有指定座位回傳 failed
訂到幾張算幾張
```

**有座位可以選 選座成功情況:**
publish to **event_ticketing_service**
```
→ 事件: SeatUpdatedToReserved
→ topic: event-id-123___:update-ticket-status-to-reserved___:event-ticketing-service
→ partition_key: event-123-section-A-partition-0 # 原子更新 RocksDB
```
publish to **booking_service:**
```
→ 事件: BookingUpdatedToPendingPayment
→ topic: event-id-123___:update-booking-status-to-pending-payment___:booking-service
→ partition_key: event-123 # 暫不分太細的 partition
```


**無座位可以選 選座失敗情況:**
publish to **booking_service:**
```
→ 事件: BookingUpdatedToFailed
→ topic: event-id-123___:booking-status-to-failed___:booking-service
→ partition_key: event-123 # 暫不分太細的 partition
```


**SSE 即時廣播:**
subsection 狀況



### 🏗️ Step 3: RocksDB 原子操作 2 server 2 consumer
**seat_reservation 內部處理流程:**
1. 透過 `partition_key: event-123-section-A-partition-0` 路由到對應的 RocksDB 實例
2. 執行原子座位預訂操作:
```
檢查: seat_state[A-1-1-1] == AVAILABLE
更新: seat_state[A-1-1-1] = RESERVED + booking_id + buyer_id + timestamp
```
3. 操作成功後，發送雙事件到不同服務



### ✅ Step 4: 後續服務處理

**event_ticketing service** 收到 topic:
- `event-id-123___:update-ticket-status-to-reserved___:event-ticketing-service`
```
根據 ticket_id 更改 PostgreSQL ticket 狀態: AVAILABLE → RESERVED
```

**booking service** 收到 topic:
- `event-id-123___:update-booking-status-to-pending-payment___:booking-service` (成功情況)
- `event-id-123___:booking-status-to-failed___:booking-service` (失敗情況)
```
根據 booking_id 更改 PostgreSQL booking 狀態:
- PROCESSING → PENDING_PAYMENT + Redis TTL (15分鐘)
- PROCESSING → FAILED
```

**SSE 即時通知 buyer:**
- 通知購票者 booking 狀態變化

### 🔄 Consumer Group 配置 (1:1:2 架構)
**統一命名規則:** `event-id-{event_id}__{service_name}-{event_id}`

- **event-id-1__booking-service-1** - 訂單服務 (1個實例)
- **event-id-1__seat-reservation-service-1** - 座位預訂服務 (1個實例)
- **event-id-1__event-ticketing-service-1** - 票務狀態管理服務 (2個實例)

**負載分配:**
```
1 booking consumer       : 處理訂單創建和狀態更新
1 seat-reservation       : 處理座位選擇算法和服務協調
2 event-ticketing        : 處理RocksDB狀態管理和PostgreSQL同步 (高負載)
```

每個 consumer group 使用統一命名，無隨機UUID後綴，確保系統可預測性和可維護性。

## 付款流程圖 

```
┌───────────────────┐                            ┌───────────────────┐
│  booking_service  │                            │  event_ticketing  │
│   (PostgreSQL)    │                            │    (PostgreSQL)   │
└───────────────────┘                            └───────────────────┘
         │                                                 │
         │                                                 │
         ▼                                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Kafka + Quix Streams + RocksDB                  │
│           Event-Driven + Stateful Stream + Lock-Free               │
└────────────────────────────────────────────────────────────────────┘
```

### 💳 Step 5: 用戶付款流程
**付款成功情況:**
1. 前端發起付款請求 → booking_service 處理付款
2. booking_service 更新狀態 (PENDING_PAYMENT → PAID)
3. 發送事件到 event_ticketing:
```
→ 事件: BookingPaidSuccess
→ topic: event-id-123___:update-ticket-status-to-paid___:event-ticketing-service
→ partition_key: event-123
```
4. event_ticketing 更新票據狀態 (RESERVED → SOLD)
5. SSE 推送 "付款成功，票據已確認" 到前端
### ⏰ Step 6: 付款超時流程 (Redis TTL 15分鐘)
1. booking_service 設置訂單狀態到 Redis (PENDING_PAYMENT, TTL=15分鐘)
2. Redis TTL 過期 → 自動刪除 PENDING_PAYMENT 狀態
3. booking_service 定期掃描過期訂單 → 更新 PostgreSQL (PENDING_PAYMENT → CANCELLED)
4. 發送單一事件給兩個服務：

**Step 4.1 - 通知 event_ticketing 釋放票據:**
```
→ 事件: BookingExpiredReleaseTickets
→ topic: event-id-123___:update-ticket-status-to-available___:event-ticketing-service
→ partition_key: event-123
→ 消費者: event_ticketing
→ 動作: 更新票據狀態 RESERVED → AVAILABLE
```

**Step 4.2 - event_ticketing 通知 seat_reservation 釋放座位:**
```
→ 事件: ReleaseSeat
→ topic: event-id-123___:release-ticket-to-available-by-rocksdb___:seat-reservation-service
→ partition_key: event-123-section-A-partition-0
→ 消費者: seat_reservation
→ 動作: 清理 RocksDB 座位狀態 RESERVED → AVAILABLE
```

5. SSE 推送 "訂單已取消" 到前端



## 技術棧
- **RocksDB + Quix Streams**: 無鎖座位狀態管理
- **Kafka**: 事件驅動微服務通信 (10 分區)
- **PostgreSQL**: 持久化存儲
- **Redis**: 付款超時管理 (TTL 15 分鐘)
- **SSE**: 實時前端通知
- **2 服務器部署**: 支持 50,000 張票高並發處理


### DI
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html

### Quix Streams
https://quix.io/docs/get-started/welcome.html
https://quix.io/docs/quix-streams/advanced/serialization.html
https://quix.io/docs/quix-streams/advanced/topics.html
https://quix.io/docs/quix-streams/advanced/stateful-processing.html