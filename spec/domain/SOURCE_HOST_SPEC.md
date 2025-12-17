# Source Host (Unity 主機) - PRD

## 1. Overview

Source Host 用於管理 Unity 主機連線資訊，儲存 FQDN、帳號、密碼等資訊，用於呼叫 Unity API 進行備份相關操作。

---

## 2. Business Rules

1. **Host 唯一性**: 每個 Unity 主機 FQDN 只能有一筆記錄
2. **密碼加密**: 密碼使用 RSA 加密後儲存
3. **刪除限制**: 正在執行作業時無法刪除
4. **並行控制**: 同一主機同時只能執行一個作業（refresh）
5. **權限控制**:
   - 查詢: 所有已登入用戶
   - 新增/修改/刪除/刷新: 僅 SuperUser

---

## 3. User Story

- 作為 SuperUser，我需要新增 Unity 主機連線資訊，以便系統能連接 Unity API 進行備份操作
- 作為 SuperUser，我需要更新 Unity 主機的帳號密碼，以便維持連線資訊的正確性
- 作為 SuperUser，我需要刪除不再使用的 Unity 主機，以便維護清單的整潔
- 作為 SuperUser，我需要刷新備份清單，以便取得最新的備份資料
- 作為已登入用戶，我需要查看所有 Unity 主機清單，以便了解系統可用的備份來源

---

## 4. Acceptance

- [ ] SuperUser 可以成功新增 Source Host
- [ ] 新增重複的 host 時回傳 400 錯誤
- [ ] 非 SuperUser 無法新增/修改/刪除/刷新 (403)
- [ ] 已登入用戶可以查看 Source Host 列表
- [ ] 正在執行作業的 Source Host 無法刪除 (400)
- [ ] 正在執行作業的 Source Host 無法再次刷新 (400)
- [ ] 密碼以 RSA 加密儲存，可用私鑰解密還原
- [ ] 輸入驗證失敗回傳 400，包含錯誤欄位說明
- [ ] is_running 狀態：refresh 開始設為 true，完成後自動設回 false

---

## 5. Test Scenarios

-> [source_host_integration_test.feature](../../tests/source_host/source_host_integration_test.feature)

---

## 6. Technical Specification

### 6.1 API Endpoints

| Method | Endpoint | Description | Permission | Success | Error |
|--------|----------|-------------|------------|---------|-------|
| GET | `/api/source_host/` | 列出所有 Source Host | Authenticated | 200 | 401 |
| POST | `/api/source_host/` | 新增 Source Host | SuperUser | 201 | 400, 403 |
| PUT | `/api/source_host/{id}/` | 更新 Source Host | SuperUser | 200 | 400, 403, 404 |
| DELETE | `/api/source_host/{id}/` | 刪除 Source Host | SuperUser | 204 | 400, 403, 404 |
| POST | `/api/source_host/{id}/refresh/` | 刷新備份清單 | SuperUser | 202 | 400, 403, 404 |

### 6.2 Model

-> [source_host_model.py](../../asdr_app/models/source_host_model.py)

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `id` | Integer | Primary key | Auto-generated |
| `host` | CharField | Unity 主機 FQDN | unique, max_length=255 |
| `account` | CharField | 登入帳號 | max_length=100 |
| `password` | BinaryField | 加密後的密碼 | Encrypted |
| `is_running` | BooleanField | 是否正在執行作業 | default=False |

### 6.3 Implementation

- [source_host_entity.py](../../asdr_app/domain/source_host/source_host_entity.py)
- [source_host_use_case.py](../../asdr_app/applications/source_host/source_host_use_case.py)
- [source_host_controller.py](../../asdr_app/inbound_adapter/http_controller/source_host_controller.py)
- [source_host_schema.py](../../asdr_app/views/schemas/source_host_schema.py)
- [source_host_repo.py](../../asdr_app/outbound_adapter/repos/source_host_repo.py)
