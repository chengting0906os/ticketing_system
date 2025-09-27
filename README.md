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
│   booking_service   │     │   seat_reservation   │     │   event_ticketing   │
│    (PostgreSQL)     │     │      (RocksDB)       │     │     (PostgreSQL)    │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
         │                           │                          │
         │                           │                          │
         ▼                           ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Kafka + Quix Streams                            │
│                   Event-Driven + Stateful Stream + Lock-Free                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 預訂流程
1. **booking_service** 創建訂單 (status: PROCESSING) → 發送 `TicketReservedRequest` 事件
2. **seat_reservation** 收到事件 → 領域服務選擇座位：
   - 如果選不到座位 → 直接發送 `TicketReserveFailed` 事件
   - 如果選到座位 → 發送座位預訂命令到 RocksDB
3. **RocksDB Processor** 執行原子操作：
   - 檢查座位狀態 (AVAILABLE → RESERVED)
   - 記錄 booking_id, buyer_id, reserved_at
   - 發送 `SeatReservationSuccess/Failed` 事件
4. **選票成功流程**:
   - seat_reservation 選票成功 → 發送兩個事件：
     - `TicketReservedSuccess` 事件到 event_ticketing_service
     - `BookingChangeStatusToPendingPayment` 事件到 booking_service
   - event_ticketing_service 同步 PostgreSQL 票據狀態 (AVAILABLE → RESERVED)
   - booking_service 更新狀態 (PROCESSING → PENDING_PAYMENT) + 設置 Redis TTL (15分鐘)
   - SSE 推送 "預訂成功，請付款" 到前端
5. **訂票失敗流程**:
   - seat_reservation 發送 `TicketReserveFailed` 事件
   - booking_service 更新狀態 (PROCESSING → FAILED)
   - SSE 推送 "座位已被預訂" 到前端

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

6. **用戶付款**: 前端發起付款請求 → booking_service 處理付款
7. **付款成功流程**:
   - booking_service 更新狀態 (PENDING_PAYMENT → PAID)
   - 發送 `BookingPaid` 事件到 event_ticketing
   - event_ticketing 更新票據狀態 (RESERVED → SOLD)
   - SSE 推送 "付款成功，票據已確認" 到前端
8. **付款超時流程** (Redis TTL 15分鐘):
   - booking_service 設置訂單狀態到 Redis (PENDING_PAYMENT, TTL=15分鐘)
   - Redis TTL 過期 → 自動刪除 PENDING_PAYMENT 狀態
   - booking_service 定期掃描過期訂單 → 更新 PostgreSQL (PROCESSING → CANCELLED)
   - 發送兩個過期事件：
     - `BookingExpired` 事件到 event_ticketing (更新票據狀態 RESERVED → AVAILABLE)
     - `SeatReleaseRequest` 事件到 seat_reservation (清理 RocksDB 狀態)
   - SSE 推送 "訂單已取消" 到前端

## 高並發部署架構 (50,000 張票 + 2 台伺服器)

```
                    Load Balancer
                         │
              ┌──────────┴──────────┐
              │                     │
         Server 1                Server 2
    ┌─────────────────┐      ┌─────────────────┐
    │  5 Partitions   │      │  5 Partitions   │
    │  P0, P1, P2     │      │  P5, P6, P7     │
    │  P3, P4         │      │  P8, P9         │
    │                 │      │                 │
    │ 25,000 tickets  │      │ 25,000 tickets  │
    │                 │      │                 │
    │ RocksDB Store   │      │ RocksDB Store   │
    │ seat-processor  │      │ seat-processor  │
    └─────────────────┘      └─────────────────┘
              │                     │
              └──────────┬──────────┘
                         │
                   Kafka Cluster
                  (10 Partitions)
```

## 技術棧
- **RocksDB + Quix Streams**: 無鎖座位狀態管理
- **Kafka**: 事件驅動微服務通信 (10 分區)
- **PostgreSQL**: 持久化存儲
- **Redis**: 付款超時管理 (TTL 15 分鐘)
- **SSE**: 實時前端通知
- **2 服務器部署**: 支持 50,000 張票高並發處理