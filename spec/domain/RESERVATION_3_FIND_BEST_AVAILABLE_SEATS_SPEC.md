# Find Best Available Seats Specification

## 1. Overview

本文件描述座位搜尋演算法的設計，用於在 Kvrocks Bitfield 中尋找最佳可用座位。

---

## 2. Algorithm Strategy

### 2.1 Priority System

```
Priority 1: 尋找 N 個連續可用座位（最佳用戶體驗）
    │
    ├── 找到 → 立即返回
    │
    └── 找不到 ↓

Priority 2: Smart Fallback - 使用最大連續區塊組合
    │
    ├── 收集所有連續區塊
    ├── 按區塊大小排序（大→小）
    ├── 組合至滿足 quantity
    │
    └── 找不到足夠座位 → 返回 nil
```

### 2.2 Bitfield Notation

```
0 = AVAILABLE (可用)
1 = RESERVED  (已預訂)

Example (5 rows × 4 cols):
┌───┬───┬───┬───┐
│ 0 │ 0 │ 1 │ 1 │  Row 1
├───┼───┼───┼───┤
│ 0 │ 0 │ 0 │ 1 │  Row 2
├───┼───┼───┼───┤
│ 1 │ 1 │ 1 │ 1 │  Row 3
├───┼───┼───┼───┤
│ 0 │ 0 │ 0 │ 0 │  Row 4
├───┼───┼───┼───┤
│ 1 │ 0 │ 0 │ 1 │  Row 5
└───┴───┴───┴───┘

Flat Bitfield: 00110001111100001001
```

### 2.3 Seat Index Calculation

**公式**: `seat_index = (row - 1) × cols + (seat_num - 1)`

```
2D Grid (5 rows × 4 cols):              Flat Bitfield:
┌─────┬─────┬─────┬─────┐               Row 1        Row 2       Row 3         Row 4           Row 5
│  0  │  1  │  2  │  3  │  Row 1        ↓            ↓           ↓             ↓               ↓
├─────┼─────┼─────┼─────┤               [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
│  4  │  5  │  6  │  7  │  Row 2        
├─────┼─────┼─────┼─────┤
│  8  │  9  │ 10  │ 11  │  Row 3
├─────┼─────┼─────┼─────┤
│ 12  │ 13  │ 14  │ 15  │  Row 4
├─────┼─────┼─────┼─────┤
│ 16  │ 17  │ 18  │ 19  │  Row 5
└─────┴─────┴─────┴─────┘

```

Example: seat_index(row=2, seat_num=3) = (2-1) × 4 + (3-1) = 6

### 2.4 Result Format

```
[row, seat_num, seat_index]

Example: [1, 3, 2]
          │  │  └── seat_index = 2（Bitfield 位置）
          │  └───── col = 3（第 3 個座位）
          └──────── row = 1（第 1 排）
```

---

## 3. Example Scenarios

### 3.1 Priority 1: 連續座位（找到）

```
Request: quantity = 3

Bitfield: 1 1 0 0 0 1
             ───── 
              ↑
          找到 3 連續

Result: seats = [[1, 3, 2], [1, 4, 3], [1, 5, 4]]
```

### 3.2 Priority 2: Smart Fallback（2+2 組合）

```
Request: quantity = 4

Bitfield: 0 0 1 1 0 0 1 1 1 1
         ───     ───
         2       2

Result: seats = [[1,1,0], [1,2,1], [1,5,4], [1,6,5]]
```

### 3.3 Priority 2: Smart Fallback（3+1 組合）

```
Request: quantity = 4

Bitfield: 0 0 0 1 0 1 1 1 1 1
         ─────   ─
         3       1

Result: seats = [[1,1,0], [1,2,1], [1,3,2], [1,5,4]]
```

### 3.4 Priority 2: Smart Fallback（分散單座）

```
Request: quantity = 4

Bitfield: 0 1 0 1 0 1 0 1 1 1
         ─   ─   ─   ─
         1   1   1   1

Result: seats = [[1,1,0], [1,3,2], [1,5,4], [1,7,6]]
```

### 3.5 Failure: 座位不足

```
Request: quantity = 4

Bitfield: 1 1 1 0 1 0 1 1 1 1
               ─   ─
               1   1

Total available: 2 seats (not enough for 4)

Result: nil
```

---

## 4. Implementation References

- [find_best_available_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/find_best_available_seats.lua) - 最佳座位搜尋 Lua Script
- [verify_manual_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/verify_manual_seats.lua) - 手動選位驗證 Lua Script
- [seat_finder.py](../../src/service/reservation/driven_adapter/state/reservation_helper/seat_finder.py) - Python 封裝
- [seat_finder_integration_test.py](../../test/service/reservation/seat_finder_integration_test.py) - 整合測試
- [seat_state_calculate_seat_index_unit_test.py](../../test/service/reservation/seat_state_calculate_seat_index_unit_test.py) - 單元測試
