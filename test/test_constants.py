"""
Test Constants - Fixed UUIDs for Testing

使用固定的 UUID7 讓測試結果可預測且容易 debug。
所有測試都應該使用這些常數而不是隨機生成 UUID。
"""

from uuid import UUID


# ============================================================================
# User IDs
# ============================================================================
TEST_BUYER_ID_1 = UUID('019a1af7-0000-7001-0000-000000000001')  # Buyer 1
TEST_BUYER_ID_2 = UUID('019a1af7-0000-7001-0000-000000000002')  # Buyer 2
TEST_BUYER_ID_3 = UUID('019a1af7-0000-7001-0000-000000000003')  # Buyer 3
TEST_SELLER_ID_1 = UUID('019a1af7-0000-7002-0000-000000000001')  # Seller 1
TEST_SELLER_ID_2 = UUID('019a1af7-0000-7002-0000-000000000002')  # Seller 2

# ============================================================================
# Event IDs
# ============================================================================
# Seed data event_id (simple and memorable for manual testing)
SEED_EVENT_ID = UUID('00000000-0000-0000-0000-000000000001')  # Seed Event (all zeros + 1)

# Test event IDs (UUID7 format for automated tests)
TEST_EVENT_ID_1 = UUID('019a1af7-0000-7003-0000-000000000001')  # Event 1
TEST_EVENT_ID_2 = UUID('019a1af7-0000-7003-0000-000000000002')  # Event 2
TEST_EVENT_ID_3 = UUID('019a1af7-0000-7003-0000-000000000003')  # Event 3
TEST_EVENT_ID_4 = UUID('019a1af7-0000-7003-0000-000000000004')  # Event 4

# ============================================================================
# Booking IDs
# ============================================================================
TEST_BOOKING_ID_1 = UUID('019a1af7-0000-7004-0000-000000000001')  # Booking 1
TEST_BOOKING_ID_2 = UUID('019a1af7-0000-7004-0000-000000000002')  # Booking 2
TEST_BOOKING_ID_3 = UUID('019a1af7-0000-7004-0000-000000000003')  # Booking 3
TEST_BOOKING_ID_4 = UUID('019a1af7-0000-7004-0000-000000000004')  # Booking 4
TEST_BOOKING_ID_5 = UUID('019a1af7-0000-7004-0000-000000000005')  # Booking 5
TEST_BOOKING_ID_6 = UUID('019a1af7-0000-7004-0000-000000000006')  # Booking 6
TEST_BOOKING_ID_10 = UUID('019a1af7-0000-7004-0000-00000000000a')  # Booking 10
TEST_BOOKING_ID_11 = UUID('019a1af7-0000-7004-0000-00000000000b')  # Booking 11
TEST_BOOKING_ID_12 = UUID('019a1af7-0000-7004-0000-00000000000c')  # Booking 12
TEST_BOOKING_ID_999 = UUID('019a1af7-0000-7004-0000-0000000003e7')  # Booking 999 (non-existent)

# ============================================================================
# Ticket IDs
# ============================================================================
TEST_TICKET_ID_1 = UUID('019a1af7-0000-7005-0000-000000000001')  # Ticket 1
TEST_TICKET_ID_2 = UUID('019a1af7-0000-7005-0000-000000000002')  # Ticket 2
TEST_TICKET_ID_101 = UUID('019a1af7-0000-7005-0000-000000000065')  # Ticket 101
TEST_TICKET_ID_102 = UUID('019a1af7-0000-7005-0000-000000000066')  # Ticket 102
TEST_TICKET_ID_201 = UUID('019a1af7-0000-7005-0000-0000000000c9')  # Ticket 201
TEST_TICKET_ID_202 = UUID('019a1af7-0000-7005-0000-0000000000ca')  # Ticket 202


# ============================================================================
# Pattern Explanation
# ============================================================================
# UUID7 格式: 019a1af7-0000-7XXX-0000-YYYYYYYYYYYY
#             ^^^^^^^^ ^^^^ ^^^^ ^^^^ ^^^^^^^^^^^^
#             |        |    |    |    └─ 後面12位數字編號 (hex)
#             |        |    |    └─ 固定為 0000 (easier to read)
#             |        |    └─ 7XXX: 7=version 7, XXX=類型碼
#             |        └─ 固定為 0000 (easier to read)
#             └─ 時間戳 (相同批次生成會一樣)
#
# 類型碼:
#   7001 = Buyer
#   7002 = Seller
#   7003 = Event
#   7004 = Booking
#   7005 = Ticket
#
# 這樣的設計讓你一眼就能看出:
# - 019a1af7-0000-7001-0000-000000000001 → 這是 Buyer ID 1
# - 019a1af7-0000-7003-0000-000000000001 → 這是 Event ID 1
# - 019a1af7-0000-7004-0000-000000000002 → 這是 Booking ID 2
