# 🚀 AWS 部署指南

## 快速開始（3 步驟）

```bash
# 1. 設定 AWS 憑證（首次）
aws configure

# 2. 一鍵部署（30 分鐘）
make deploy

# 3. 測完關閉
make destroy
```

---

## 部署內容

- **Aurora Serverless v2**: 2-64 ACU，I/O-Optimized
- **Amazon MSK**: 3 × kafka.m5.large
- **Kvrocks**: 單 Master，4 vCPU + 8GB
- **ECS Ticketing**: 8 vCPU + 16GB + 16 workers（4-16 tasks）
- **ECS Reservation**: 2 vCPU + 4GB（4-16 tasks）
- **AWS X-Ray**: 分散式追蹤（已配置 ADOT Collector sidecars）

---

## 測試流程

```bash
# Terminal 1: 監控
make monitor

# Terminal 2: Load Test
make k6-load

# Terminal 3: X-Ray Service Map (us-west-2)
# https://us-west-2.console.aws.amazon.com/xray/home?region=us-west-2
```

---

## 成本

- **測試 1 小時**: $3-5
- **忘記關閉 1 天**: $72-120
- **⚠️ 測完務必**: `make destroy`

---

## 詳細說明

需要時看部署腳本：
- `deployment/deploy-all.sh` - 完整部署流程
- `deployment/destroy-all.sh` - 清理資源

---

## 常見問題

**Q: 需要設定 GitHub Actions 嗎？**
A: 不需要。`make deploy` 就夠了。

**Q: 部署失敗怎麼辦？**
A: 執行 `make destroy` 清理，然後重新 `make deploy`

**Q: 如何查看服務狀態？**
A: `make monitor` 即時監控

**Q: 如何查看 ALB endpoint？**
A: `jq -r '.TicketingECSStack.ALBEndpoint' deployment/cdk-outputs.json`

---

## 重要提醒

✅ 測試場景用本地部署（`make deploy`），不需要 GitHub Actions
✅ 部署完會自動建立 ADOT Collector，X-Ray 可直接使用
✅ 測試完**一定要** `make destroy` 停止計費
✅ Kvrocks 已簡化為單 Master（測試夠用）
✅ Aurora 使用 I/O-Optimized（高吞吐省成本）

---

**現在開始**：`make deploy` 🚀
