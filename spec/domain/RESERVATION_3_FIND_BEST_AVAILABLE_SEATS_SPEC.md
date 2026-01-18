# Find Best Available Seats Specification

## 1. Overview

This document describes the seat search algorithm design for finding best available seats in Kvrocks Bitfield.

---

## 2. Algorithm Strategy

### 2.1 Priority System

```
Priority 1: Find N consecutive available seats (best user experience)
    │
    ├── Found → return immediately
    │
    └── Not found ↓

Priority 2: Smart Fallback - use largest consecutive block combination
    │
    ├── Collect all consecutive blocks
    ├── Sort by block size (large → small)
    ├── Combine until quantity satisfied
    │
    └── Not enough seats → return nil
```

### 2.2 Bitfield Notation

```
0 = AVAILABLE
1 = RESERVED

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

**Formula**: `seat_index = (row - 1) × cols + (seat_num - 1)`

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
          │  │  └── seat_index = 2 (Bitfield position)
          │  └───── col = 3 (3rd seat)
          └──────── row = 1 (1st row)
```

---

## 3. Example Scenarios

### 3.1 Priority 1: Consecutive Seats (Found)

```
Request: quantity = 3

Bitfield: 1 1 0 0 0 1
             ─────
              ↑
          Found 3 consecutive

Result: seats = [[1, 3, 2], [1, 4, 3], [1, 5, 4]]
```

### 3.2 Priority 2: Smart Fallback (2+2 Combination)

```
Request: quantity = 4

Bitfield: 0 0 1 1 0 0 1 1 1 1
         ───     ───
         2       2

Result: seats = [[1,1,0], [1,2,1], [1,5,4], [1,6,5]]
```

### 3.3 Priority 2: Smart Fallback (3+1 Combination)

```
Request: quantity = 4

Bitfield: 0 0 0 1 0 1 1 1 1 1
         ─────   ─
         3       1

Result: seats = [[1,1,0], [1,2,1], [1,3,2], [1,5,4]]
```

### 3.4 Priority 2: Smart Fallback (Scattered Singles)

```
Request: quantity = 4

Bitfield: 0 1 0 1 0 1 0 1 1 1
         ─   ─   ─   ─
         1   1   1   1

Result: seats = [[1,1,0], [1,3,2], [1,5,4], [1,7,6]]
```

### 3.5 Failure: Insufficient Seats

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

- [find_best_available_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/find_best_available_seats.lua)
- [verify_manual_seats.lua](../../src/service/reservation/driven_adapter/state/reservation_helper/lua_scripts/verify_manual_seats.lua)
- [seat_finder.py](../../src/service/reservation/driven_adapter/state/reservation_helper/seat_finder.py)
- [seat_finder_integration_test.py](../../test/service/reservation/seat_finder_integration_test.py)
- [seat_state_calculate_seat_index_unit_test.py](../../test/service/reservation/seat_state_calculate_seat_index_unit_test.py)
