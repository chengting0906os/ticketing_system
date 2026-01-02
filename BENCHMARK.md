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

| 環境                         | 測試紀錄 (s)             | 平均秒數 | 平均 TPS |
| ---------------------------- | ------------------------ | -------- | -------- |
| 本地                         | 1.29/1.33/1.39/1.27/1.35 | 1.33     | 1504     |
| RDS Single-AZ                | 2.50/2.45/2.48/2.46/2.45 | 2.47     | 810      |
| RDS Single-AZ (m8gd.2xlarge) | 2.29/2.30/2.34/2.35/2.29 | 2.31     | 866      |
| RDS Single-AZ (m8gd.4xlarge) | 2.35/2.40/2.41/2.38/2.41 | 2.39     | 837      |
| RDS Multi-AZ Instance        | 3.37/3.40/3.41/3.49/3.45 | 3.42     | 585      |
| RDS Multi-AZ (m8gd.2xlarge)  | 3.51/3.38/3.47/3.41/3.46 | 3.45     | 580      |
| RDS Multi-AZ Cluster         | -/-/-/-/-                | -        | -        |

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

| 環境                  | 測試紀錄 (s)             | 平均秒數 | 平均 TPS |
| --------------------- | ------------------------ | -------- | -------- |
| RDS Single-AZ         | 6.03/6.11/6.10/6.11/6.07 | 6.08     | 822      |
| RDS Single-AZ (m8gd)  | 5.56/5.60/5.74/5.55/5.73 | 5.64     | 887      |
| RDS Multi-AZ Instance | -/-/-/-/-                | -        | -        |
| RDS Multi-AZ Cluster  | -/-/-/-/-                | -        | -        |

---

### 測試情境：規模比較 (m8gd Single-AZ)

**測試目的：**

1. 比較不同票數規模下的 TPS 穩定性
2. 驗證系統在更大數據量下的線性擴展能力

**測試條件：**

- 測試環境：RDS Single-AZ db.m8gd.2xlarge (PostgreSQL 17.5)
- 測試方式：Go spike test, fire-and-forget (< 1s 內瞬間發送全部請求)
- 測試 API：`POST /api/booking`（每次購買一張）
- 並行 workers：100
- 測試次數：5 次，取平均值

| 票數   | 測試紀錄 (s)                  | 平均秒數 | 平均 TPS |
| ------ | ----------------------------- | -------- | -------- |
| 2,000  | 2.29/2.30/2.34/2.35/2.29      | 2.31     | 866      |
| 5,000  | 5.56/5.60/5.74/5.55/5.73      | 5.64     | 887      |
| 10,000 | 11.31/11.21/11.15/11.39/11.22 | 11.26    | 888      |

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

## 效能比較分析

### 環境間比較 (2000 張票基準)

| 環境                         | 平均秒數 | TPS  | 相對本地 | 延遲增加 |
| ---------------------------- | -------- | ---- | -------- | -------- |
| 本地                         | 1.33s    | 1504 | 100%     | -        |
| RDS Single-AZ (m8gd.2xlarge) | 2.31s    | 866  | 58%      | +74%     |
| RDS Multi-AZ (m8gd.2xlarge)  | 3.45s    | 580  | 39%      | +159%    |

### 關鍵發現

1. **網路延遲影響**：雲端環境比本地慢約 74%，主要來自網路 RTT
2. **Multi-AZ 代價**：同步複寫導致額外 33% TPS 損失 (866 → 580)
3. **升級 CPU 無效**：m8gd.4xlarge (837 TPS) 比 m8gd.2xlarge (866 TPS) 還慢，瓶頸不在 DB CPU
4. **TPS 穩定性**：TPS 在 2K/5K/10K 票數下維持穩定 (~880)，不因資料量增加而下降

### 結論

- 生產環境建議使用 **RDS Single-AZ + m8gd.2xlarge**，性價比最佳
- Multi-AZ 僅在需要高可用時使用，需接受 33% 效能損失
- 瓶頸在網路層，非資料庫運算能力

---
