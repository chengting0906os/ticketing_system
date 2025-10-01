# Distributed Ticketing System
A high-performance event ticketing platform built with Clean Architecture, BDD/TDD principles, and event-driven microservices.

## System Overview
**Capacity**: 50,000 tickets per event
**Architecture**: 3 microservices + Kvrocks Bitfield + Counter + Kafka
**Concurrency**: Lock-free seat reservations
**Deployment**: 2 servers with 10 Kafka partitions

## Core Features
- **Real-time seat reservation** with atomic Kvrocks Bitfield + Counter operations
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

## 三微服務架構 + Kvrocks Bitfield + Counter 無鎖預訂

```
┌─────────────────────┐   ┌────────────────────────────────────────┐   ┌─────────────────────┐
│   booking_service   │──▶│       seat_reservation_service         │──▶│   event_ticketing   │
│    (PostgreSQL)     │   │      🎯 Algo + Kvrocks Bitfield          │   │    (PostgreSQL)     │
│                     │◀──│                                        │◀──│                     │
│  📊 Consumer: 1     │   │         📊 Consumer: 2                  │   │  📊 Consumer: 1     │
│ event-id-1_____     │   │ event-id-1_____seat-reservation-       │   │ event-id-1_____     │
│ booking-service--1  │   │ service--1                             │   │ event-ticketing-    │
│                     │   │                                        │   │ service--1          │
└─────────────────────┘   └────────────────────────────────────────┘   └─────────────────────┘
         │                                    │                                  │
         │                                    │                                  │
         ▼                                    ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Kafka + Quix Streams                                       │
│                        Event-Driven + Stateful Stream + Lock-Free                           │
│                              🔄 1:1:1 Consumer Architecture                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Topic 和 Partition 策略

### 📡 Topic 命名格式
```
event-id-{event_id}______{action}______{from_service}___to___{to_service}
例如：event-id-123______ticket-reserving-request-in-kvrocks______booking-service___to___seat-reservation-service
例如：event-id-123______update-ticket-status-to-reserved-in-postgresql______seat-reservation-service___to___event-ticketing-service
```

**命名規範：**
- 以 `-in-kvrocks` 結尾：操作 Kvrocks Bitfield + Counter 狀態（即時座位選擇）
- 以 `-in-postgresql` 結尾：操作 PostgreSQL（持久化票務記錄）

### 🎯 Partition Key 格式
```
event-{event_id}-section-{section}-partition-{partition_number}
例如：event-123-section-A-partition-0
```

### 🗂️ 主要 Topics

#### To Seat Reservation Service (Kvrocks Bitfield + Counter 操作)
- `event-id-{event_id}______ticket-reserving-request-in-kvrocks______booking-service___to___seat-reservation-service` - 票據預訂請求（Kvrocks Bitfield + Counter 座位選擇）
- `event-id-{event_id}______release-ticket-status-to-available-in-kvrocks______event-ticketing-service___to___seat-reservation-service` - 釋放座位狀態為可用（Kvrocks Bitfield + Counter）
- `event-id-{event_id}______finalize-ticket-status-to-paid-in-kvrocks______event-ticketing-service___to___seat-reservation-service` - 確認座位為已付款（Kvrocks Bitfield + Counter）
- `event-id-{event_id}______seat-initialization-command-in-kvrocks______event-ticketing-service___to___seat-reservation-service` - 座位初始化指令（Kvrocks Bitfield + Counter）

#### To Event Ticketing Service (PostgreSQL 操作)
- `event-id-{event_id}______update-ticket-status-to-reserved-in-postgresql______seat-reservation-service___to___event-ticketing-service` - 更新票據狀態為預訂（PostgreSQL）
- `event-id-{event_id}______update-ticket-status-to-paid-in-postgresql______booking-service___to___event-ticketing-service` - 更新票據狀態為已付款（PostgreSQL）
- `event-id-{event_id}______update-ticket-status-to-available-in-kvrocks______booking-service___to___event-ticketing-service` - 更新票據狀態為可用（注：此處雖命名含 rocksdb，但實際目標是 event_ticketing）

#### To Booking Service
- `event-id-{event_id}______update-booking-status-to-pending-payment______seat-reservation-service___to___booking-service` - 更新訂單狀態為待付款
- `event-id-{event_id}______update-booking-status-to-failed______seat-reservation-service___to___booking-service` - 訂單狀態為失敗

### ⚡ 區域集中式 Partition 策略
- **A區所有座位** → 固定 partition (例如 partition-0)
- **B區所有座位** → 固定 partition (例如 partition-1)
- **同區域查詢效率極高** → 只需查詢單一 partition
- **原子性保證** → 區域內座位操作在同一 Kvrocks Bitfield + Counter instance



## 詳細預訂流程

### 🎫 Step 1: booking service 訂單創建 1 server 1 consumer
**booking_service** 創建訂單:
```
→ booking raw create and status: PROCESSING
→ 發送事件到: event-id-123______ticket-reserving-request-in-kvrocks______booking-service___to___seat-reservation-service
→ partition_key: event-123-section-A-partition-0 # booking_service 透過 partition_key 分流到不同 consumer/partition
→ 事件: TicketReservedRequest(**booking_data)
→ return booking detail 200
```

### 🪑 Step 2: seat_reservation service (Kvrocks Bitfield + Counter + Algorithm)
**seat_reservation**
收到 topic event-id-123______ticket-reserving-request-in-kvrocks______booking-service___to___seat-reservation-service 

**seat selection service 查詢座位 strategry**
exactly once sequential processing
- best-available
```
讀取座位狀況
連續座位先找同排座位
沒有就 / 2 拆散
直到全部找到座位或選到幾張算幾張
透過 partition_key 原子更新 Kvrocks Bitfield + Counter 座位
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
→ topic: event-id-123______update-ticket-status-to-reserved-in-postgresql______seat-reservation-service___to___event-ticketing-service
→ partition_key: event-123-section-A-partition-0 # 持久化到 PostgreSQL
```
publish to **booking_service:**
```
→ 事件: BookingUpdatedToPendingPayment
→ topic: event-id-123______update-booking-status-to-pending-payment______seat-reservation-service___to___booking-service
→ partition_key: event-123 # 暫不分太細的 partition
```


**無座位可以選 選座失敗情況:**
publish to **booking_service:**
```
→ 事件: BookingUpdatedToFailed
→ topic: event-id-123______update-booking-status-to-failed______seat-reservation-service___to___booking-service
→ partition_key: event-123 # 暫不分太細的 partition
```


**SSE 即時廣播:**
subsection 狀況



### 🏗️ Step 3: Kvrocks Bitfield + Counter 原子操作 2 server 2 consumer
**seat_reservation 內部處理流程:**
1. 透過 `partition_key: event-123-section-A-partition-0` 路由到對應的 Kvrocks Bitfield + Counter 實例
2. 執行原子座位預訂操作:
```
檢查: seat_state[A-1-1-1] == AVAILABLE
更新: seat_state[A-1-1-1] = RESERVED + booking_id + buyer_id + timestamp
```
3. 操作成功後，發送雙事件到不同服務



### ✅ Step 4: 後續服務處理

**event_ticketing service** 收到 topic:
- `event-id-123______update-ticket-status-to-reserved-in-postgresql______seat-reservation-service___to___event-ticketing-service`
```
根據 ticket_id 更改 PostgreSQL ticket 狀態: AVAILABLE → RESERVED
```

**booking service** 收到 topic:
- `event-id-123______update-booking-status-to-pending-payment______seat-reservation-service___to___booking-service` (成功情況)
- `event-id-123______update-booking-status-to-failed______seat-reservation-service___to___booking-service` (失敗情況)
```
根據 booking_id 更改 PostgreSQL booking 狀態:
- PROCESSING → PENDING_PAYMENT + Redis TTL (15分鐘)
- PROCESSING → FAILED
```

**SSE 即時通知 buyer:**
- 通知購票者 booking 狀態變化

### 🔄 Consumer Group 配置 (1:2:1 架構)
**統一命名規則:** `event-id-{event_id}_____{service_name}--{event_id}`

- **event-id-1_____booking-service--1** - 訂單服務 (1個實例) - PostgreSQL
- **event-id-1_____seat-reservation-service--1** - 座位預訂服務 (2個實例) - Kvrocks Bitfield + Counter + 選座算法
- **event-id-1_____event-ticketing-service--1** - 票務管理服務 (1個實例) - PostgreSQL

**職責分配:**
```
1 booking consumer        : 處理訂單創建和狀態更新 (PostgreSQL)
2 seat-reservation        : 處理座位選擇算法 + Kvrocks Bitfield + Counter 即時狀態管理 (高並發)
1 event-ticketing         : 處理票務持久化到 PostgreSQL
```

**架構變更亮點:**
- `seat_reservation` 現在擁有自己的 Kvrocks Bitfield + Counter，負責座位即時狀態查詢和選座算法
- `event_ticketing` 簡化為只負責 PostgreSQL 的票務持久化
- 狀態管理責任清晰分離：Kvrocks Bitfield + Counter (即時) vs PostgreSQL (持久化)

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
│             Kafka + Quix Streams + Kvrocks Bitfield                 │
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
→ topic: event-id-123______update-ticket-status-to-paid-in-postgresql______booking-service___to___event-ticketing-service
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
→ topic: event-id-123______update-ticket-status-to-available-in-kvrocks______booking-service___to___event-ticketing-service
→ partition_key: event-123
→ 消費者: event_ticketing
→ 動作: 更新票據狀態 RESERVED → AVAILABLE (PostgreSQL)
```

**Step 4.2 - event_ticketing 通知 seat_reservation 釋放座位:**
```
→ 事件: ReleaseSeat
→ topic: event-id-123______release-ticket-status-to-available-in-kvrocks______event-ticketing-service___to___seat-reservation-service
→ partition_key: event-123-section-A-partition-0
→ 消費者: seat_reservation
→ 動作: 清理 Kvrocks Bitfield + Counter 座位狀態 RESERVED → AVAILABLE
```

5. SSE 推送 "訂單已取消" 到前端



## 技術棧
- **Kvrocks Bitfield + Counter + Quix Streams**: 無鎖座位狀態管理
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

---

## 📦 Kvrocks 資料結構設計

### 設計目標
針對 **50,000 座位的大型活動**（例如：A-1 到 J-10，每區 500 座位），實現：
- **極致壓縮**: Bitfield 2 bits per seat
- **毫秒查詢**: Counter O(1) 統計
- **高併發**: 無鎖設計，100,000+ QPS
- **零丟失**: Kvrocks (RocksDB) 持久化

---

### 資料結構總覽

```
活動 1 (50,000 座位)
├── A-1 (500 座位)
│   ├── seats_bf:1:A-1              ← Bitfield (125 bytes) - 精確座位狀態
│   ├── subsection_avail:1:A-1      ← Counter "490" - O(1) 可售數查詢
│   ├── subsection_total:1:A-1      ← Metadata "500" - 固定總數
│   ├── row_avail:1:A-1:1           ← Counter "20" - 排級別可售數
│   ├── row_avail:1:A-1:2           ← Counter "20"
│   ├── ...
│   ├── seat_meta:1:A-1:1           ← Hash {1:3000, 2:3000...} - 價格
│   └── seat_meta:1:A-1:25          ← Hash {1:3000, 2:3000...}
│
├── A-2 (500 座位)
│   ├── seats_bf:1:A-2
│   ├── subsection_avail:1:A-2
│   └── ...
│
└── J-10 (500 座位, 第 100 個 subsection)
    ├── seats_bf:1:J-10
    ├── subsection_avail:1:J-10
    └── ...
```

---

### 1️⃣ Bitfield - 精確座位狀態

**Key 格式:**
```
seats_bf:{event_id}:{section}-{subsection}
```

**用途:** 存儲每個座位的精確狀態
**大小:** 500 座位 × 2 bits = 1,000 bits = **125 bytes**
**類型:** String (用作 Bitfield)

**座位狀態編碼 (2 bits):**
```
0 (00) = AVAILABLE    可售
1 (01) = RESERVED     已預訂
2 (10) = SOLD         已售出
3 (11) = UNAVAILABLE  不可售
```

**座位索引計算:**
```python
# 座位 ID: A-1-5-10
# (section=A, subsection=1, row=5, seat=10)

seat_index = (row - 1) * 20 + (seat_num - 1)
           = (5 - 1) * 20 + (10 - 1)
           = 89

bit_offset = seat_index * 2 = 178
```

**操作範例:**
```bash
# 設定座位 #89 為 RESERVED (1)
BITFIELD seats_bf:1:A-1 SET u2 178 1

# 讀取座位 #89 狀態
BITFIELD seats_bf:1:A-1 GET u2 178
# 返回: [1] → RESERVED
```

**實際數據範例:**
```
座位 A-1-1-1  (第1排第1座) → bit offset 0    → 值 0 (AVAILABLE)
座位 A-1-1-2  (第1排第2座) → bit offset 2    → 值 1 (RESERVED)
座位 A-1-1-3  (第1排第3座) → bit offset 4    → 值 0 (AVAILABLE)
...
座位 A-1-25-20 (第25排第20座) → bit offset 998 → 值 2 (SOLD)
```

---

### 2️⃣ Subsection Counter - 區級可售數

**Key 格式:**
```
subsection_avail:{event_id}:{section}-{subsection}
```

**範例:**
```redis
subsection_avail:1:A-1 = "490"
```

**用途:** O(1) 快速查詢整個區還有多少座位可售
**類型:** String (整數)
**範圍:** 0-500

**更新邏輯:**
```python
# 初始化座位 (AVAILABLE)
INCR subsection_avail:1:A-1  # +1

# 預訂座位 (AVAILABLE → RESERVED)
DECR subsection_avail:1:A-1  # -1

# 取消預訂 (RESERVED → AVAILABLE)
INCR subsection_avail:1:A-1  # +1
```

---

### 3️⃣ Subsection Total - 區級總座位數

**Key 格式:**
```
subsection_total:{event_id}:{section}-{subsection}
```

**範例:**
```redis
subsection_total:1:A-1 = "500"
```

**用途:** 記錄這個區總共有多少座位（固定值，初始化時寫入一次）
**類型:** String (整數)
**寫入時機:** 創建活動發送座位初始化事件前

---

### 4️⃣ Row Counter - 排級可售數

**Key 格式:**
```
row_avail:{event_id}:{section}-{subsection}:{row}
```

**範例:**
```redis
row_avail:1:A-1:5 = "18"
```

**用途:** 座位選擇算法用，快速判斷某排是否有足夠座位
**類型:** String (整數)
**範圍:** 0-20

**使用場景:**
```python
# 尋找 2 個連續座位
for row in range(1, 26):
    count = GET row_avail:1:A-1:{row}
    if count >= 2:
        # 這排可能有連續座位，進一步檢查 Bitfield
        ...
```

---

### 5️⃣ Seat Metadata - 價格資訊

**Key 格式:**
```
seat_meta:{event_id}:{section}-{subsection}:{row}
```

**範例:**
```redis
seat_meta:1:A-1:5
Type: Hash
Value: {
  "1": "3000",
  "2": "3000",
  ...
  "20": "3000"
}
```

**用途:** 存儲每個座位的價格
**類型:** Hash
**欄位:** {seat_num: price}

---

## 🎯 實際使用場景

### 場景 1: API 查詢「A-1 區統計資訊」

**API:** `GET /api/seat_reservation/1/tickets/section/A/subsection/1`

**查詢邏輯:**
```python
# 只需 2 次 Redis GET 操作
available = GET subsection_avail:1:A-1    # "490"
total = GET subsection_total:1:A-1        # "500"

# 計算
unavailable = total - available           # 500 - 490 = 10

# 回傳
{
  "total": 500,
  "available": 490,
  "reserved": 10,
  "sold": 0
}
```

**性能指標:**
- **延遲:** 1-2ms
- **複雜度:** O(1)
- **Redis 操作:** 2 次 GET

---

### 場景 2: 預訂座位 A-1-5-10

**操作流程:**
```python
# 1. 計算 bit offset
seat_index = (5-1)*20 + (10-1) = 89
bit_offset = 89 * 2 = 178

# 2. 更新 Bitfield (AVAILABLE → RESERVED)
BITFIELD seats_bf:1:A-1 SET u2 178 1

# 3. 更新 Counter
DECR row_avail:1:A-1:5           # 20 → 19
DECR subsection_avail:1:A-1      # 490 → 489
```

**性能指標:**
- **延遲:** ~1ms
- **Redis 操作:** 3 次寫入
- **原子性:** 透過 Kafka partition key 保證

---

### 場景 3: 座位選擇算法「找 2 個連續座位」

**算法流程:**
```python
# 1. 快速掃描各排的可售數 (O(25))
for row in range(1, 26):
    count = GET row_avail:1:A-1:{row}
    if count >= 2:
        # 2. 讀取該排的 Bitfield 找連續座位
        for seat in range(1, 20):
            offset1 = ((row-1)*20 + (seat-1)) * 2
            offset2 = ((row-1)*20 + seat) * 2

            status1 = BITFIELD seats_bf:1:A-1 GET u2 {offset1}
            status2 = BITFIELD seats_bf:1:A-1 GET u2 {offset2}

            if status1 == 0 and status2 == 0:
                # 找到連續座位！
                return [(row, seat), (row, seat+1)]
```

**性能指標:**
- **最佳情況:** 第 1 排就找到 → ~5ms
- **最壞情況:** 掃描全部 25 排 → ~50ms
- **平均情況:** ~20ms

---

## 📊 記憶體估算

### 單個 Subsection (500 座位)
```
seats_bf:1:A-1              125 bytes   (Bitfield)
subsection_avail:1:A-1      10 bytes    (String "490")
subsection_total:1:A-1      10 bytes    (String "500")
row_avail:1:A-1:1-25        250 bytes   (25 個 Counter)
seat_meta:1:A-1:1-25        ~2 KB       (25 個 Hash)
─────────────────────────────────────────────────
總計                         ~2.4 KB
```

### 整個活動 (100 subsections, 50,000 座位)
```
2.4 KB × 100 subsections = 240 KB
```

**對比:**
- 傳統方案 (每座位一個 Hash): ~50 MB
- Bitfield 方案: **240 KB**
- **壓縮比: 200:1** 🎉

---

## ⚡ 性能指標總結

| 操作 | 延遲 | 複雜度 | Redis 操作數 |
|------|------|--------|-------------|
| 查詢區統計 | 1-2ms | O(1) | 2 GET |
| 預訂單個座位 | ~1ms | O(1) | 3 寫入 |
| 尋找連續座位 | 10-50ms | O(n) | 25-500 讀取 |
| 批量初始化 500 座位 | ~500ms | O(n) | 1500 寫入 |

**吞吐量:**
- **讀取查詢:** 100,000+ QPS
- **座位預訂:** 50,000+ TPS
- **併發支援:** 無鎖設計，理論無上限

---

## 🔑 設計優勢

1. **極致壓縮**
   - Bitfield 2 bits per seat
   - 500 座位僅 125 bytes
   - 壓縮比 200:1

2. **毫秒查詢**
   - Counter O(1) 統計
   - 無需掃描 Bitfield
   - 1-2ms 響應時間

3. **高併發友好**
   - 無鎖設計
   - Partition 隔離
   - 100,000+ QPS

4. **零數據丟失**
   - Kvrocks = RocksDB 持久化
   - AOF + Snapshot
   - 生產級可靠性

5. **可擴展性**
   - 支援 50,000 座位/活動
   - 水平擴展 (Partition)
   - 記憶體佔用極低

---