# 票務系統效能基準測試

## 測試環境

### 本地開發環境

| 組件                | 規格                                        |
| ------------------- | ------------------------------------------- |
| 機器                | MacBook Pro (Apple M2 Max, 12 cores, 32 GB) |
| PostgreSQL          | Docker                                      |
| Kafka               | 3 brokers (Docker)                          |
| Kvrocks             | Docker                                      |
| Ticketing Service   | 5 instances                                 |
| Reservation Service | 5 instances                                 |

### AWS 雲端環境 (Development)

| 組件                | 規格                                                      |
| ------------------- | --------------------------------------------------------- |
| 區域                | us-west-2                                                 |
| RDS PostgreSQL      | db.c6gd.2xlarge (8 vCPU, 32 GB RAM, Graviton2 ARM + NVMe) |
| Kafka               | 3x c7g.large EC2 (2 vCPU, 4 GB RAM, ARM Graviton3)        |
| Kvrocks             | m6i.large EC2 (2 vCPU, 8 GB RAM, x86 Intel)               |
| Ticketing Service   | ECS Fargate (2 vCPU, 4 GB)                                |
| Reservation Service | ECS Fargate (2 vCPU, 4 GB)                                |
| Load Balancer       | Application Load Balancer (ALB)                           |
| Load Test Client    | c7g.xlarge EC2 (4 vCPU, 8 GB RAM, ARM Graviton3)          |

---

## 基準測試結果

### 測試情境：尖峰測試 (全席售罄)

**測試目的：**

1. 建立各環境的效能基準線
2. 比較本地與雲端環境的 TPS 差異

**測試條件：**

- 總票數：2000 張
- 測試方式：Go spike test, fire-and-forget (< 0.1s 內瞬間發送全部請求)
- 測試 API：`POST /api/booking`（每次購買一張）
- 並行 workers：100
- 測試次數：5 次，取平均值

| 環境   | 測試紀錄 (s)             | 平均秒數 | 平均 TPS |
| ------ | ------------------------ | -------- | -------- |
| 本地   | 1.29/1.33/1.39/1.27/1.35 | 1.33     | 1504     |
| RDS    | -/-/-/-/-                | -        | -        |
| RDS+1R | -/-/-/-/-                | -        | -        |
| RDS+2R | -/-/-/-/-                | -        | -        |

> **備註**：本地環境極限約 2000 張票。超過此數量 API 層無法即時消化請求，回應時間會大幅增加。

---

### 測試情境：擴展性驗證 (5000 張)

**測試目的：**

1. 驗證服務端 TPS 是否穩定
2. 確認 PostgreSQL/Kvrocks 在更大數據量下沒有掉速

**測試條件：**

- 總票數：5000 張
- 測試方式：Go spike test, fire-and-forget (< 0.1s 內瞬間發送全部請求)
- 測試 API：`POST /api/booking`（每次購買一張）
- 並行 workers：100
- 測試次數：5 次，取平均值

| 環境   | 測試紀錄 (s) | 平均秒數 | 平均 TPS |
| ------ | ------------ | -------- | -------- |
| RDS    | -/-/-/-/-    | -        | -        |
| RDS+1R | -/-/-/-/-    | -        | -        |
| RDS+2R | -/-/-/-/-    | -        | -        |

---

### 測試情境：持續負載測試 (k6 Load Test)

**測試目的：**

1. 在維持 0% 錯誤率的前提下，找出系統可承受的最高 RPS
2. 測量 p95/p99 延遲表現

**測試條件：**

- 總票數：200,000 張
- 測試方式：k6 ramping-arrival-rate (500→1400→1000 req/s)
- 測試 API：`POST /api/booking`（每次隨機購買 1~4 張）
- 最大 VUs：依環境調整（本地 1400）
- 測試時長：60s

| 環境 | 總請求 | RPS   | avg 延遲 | p95 延遲 | p99 延遲 |
| ---- | ------ | ----- | -------- | -------- | -------- |
| 本地 | 68,713 | 1,145 | 68ms     | 163ms    | 249ms    |
| ECS  | -      | -     | -        | -        | -        |

---
