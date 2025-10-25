@integration
Feature: Booking List
  As a buyer
  I want to list my bookings with details
  So that I can track my purchases

  As a seller
  I want to list bookings for my events
  So that I can track my sales

  Background:
    Given users exist:
      | email            | password | name         | role   | id                                   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller | 019a1af7-0000-7002-0000-000000000001 |
      | seller2@test.com | P@ssw0rd | Test Seller2 | seller | 019a1af7-0000-7002-0000-000000000002 |
      | buyer1@test.com  | P@ssw0rd | Test Buyer1  | buyer  | 019a1af7-0000-7001-0000-000000000001 |
      | buyer2@test.com  | P@ssw0rd | Test Buyer2  | buyer  | 019a1af7-0000-7001-0000-000000000002 |
      | buyer3@test.com  | P@ssw0rd | Test Buyer3  | buyer  | 019a1af7-0000-7001-0000-000000000003 |
    And events exist:
      | name    | seller_id                            | status    | id                                   | venue_name   | seating_config                                                                                 |
      | Event A | 019a1af7-0000-7002-0000-000000000001 | sold_out  | 019a1af7-0000-7003-0000-000000000001 | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
      | Event B | 019a1af7-0000-7002-0000-000000000001 | sold_out  | 019a1af7-0000-7003-0000-000000000002 | Taipei Dome  | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
      | Event C | 019a1af7-0000-7002-0000-000000000002 | sold_out  | 019a1af7-0000-7003-0000-000000000003 | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
      | Event D | 019a1af7-0000-7002-0000-000000000001 | available | 019a1af7-0000-7003-0000-000000000004 | Taipei Dome  | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    And bookings exist:
      | buyer_id                             | event_id                             | total_price | status          | paid_at  | id                                   |
      | 019a1af7-0000-7001-0000-000000000001 | 019a1af7-0000-7003-0000-000000000001 |        1000 | paid            | not_null | 019a1af7-0000-7004-0000-000000000001 |
      | 019a1af7-0000-7001-0000-000000000001 | 019a1af7-0000-7003-0000-000000000002 |        2000 | paid            | not_null | 019a1af7-0000-7004-0000-000000000002 |
      | 019a1af7-0000-7001-0000-000000000001 | 019a1af7-0000-7003-0000-000000000003 |        3000 | pending_payment | null     | 019a1af7-0000-7004-0000-000000000003 |
      | 019a1af7-0000-7001-0000-000000000002 | 019a1af7-0000-7003-0000-000000000004 |        4000 | cancelled       | null     | 019a1af7-0000-7004-0000-000000000004 |

  @smoke
  Scenario: Buyer lists their bookings
    When buyer with id 019a1af7-0000-7001-0000-000000000001 requests their bookings:
      | email           | password |
      | buyer1@test.com | P@ssw0rd |
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 3 |
    And the bookings should include:
      | id                                   | event_name | total_price | status          | seller_name  | venue_name   | section | subsection | quantity | seat_selection_mode | created_at | paid_at  |
      | 019a1af7-0000-7004-0000-000000000001 | Event A    |        1000 | paid            | Test Seller1 | Taipei Arena | A       |          1 |        1 | best_available      | not_null   | not_null |
      | 019a1af7-0000-7004-0000-000000000002 | Event B    |        2000 | paid            | Test Seller1 | Taipei Dome  | B       |          2 |        1 | best_available      | not_null   | not_null |
      | 019a1af7-0000-7004-0000-000000000003 | Event C    |        3000 | pending_payment | Test Seller2 | Taipei Arena | C       |          3 |        1 | best_available      | not_null   | null     |

  Scenario: Seller lists bookings for their events
    When seller with id 019a1af7-0000-7002-0000-000000000001 requests their bookings
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 3 |
    And the bookings should include:
      | id                                   | event_name | total_price | status    | buyer_name  | venue_name   | section | subsection | quantity | seat_selection_mode | created_at | paid_at  |
      | 019a1af7-0000-7004-0000-000000000001 | Event A    |        1000 | paid      | Test Buyer1 | Taipei Arena | A       |          1 |        1 | best_available      | not_null   | not_null |
      | 019a1af7-0000-7004-0000-000000000002 | Event B    |        2000 | paid      | Test Buyer1 | Taipei Dome  | B       |          2 |        1 | best_available      | not_null   | not_null |
      | 019a1af7-0000-7004-0000-000000000004 | Event D    |        4000 | cancelled | Test Buyer2 | Taipei Dome  | D       |          4 |        1 | best_available      | not_null   | null     |

  Scenario: Buyer with no bookings gets empty list
    When buyer with id 019a1af7-0000-7001-0000-000000000003 requests their bookings
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 0 |

  Scenario: Filter bookings by status - paid bookings only
    When buyer with id 019a1af7-0000-7001-0000-000000000001 requests their bookings with status "paid"
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 2 |
    And all bookings should have status:
      | paid |

  Scenario: Filter bookings by status - pending payment only
    When buyer with id 019a1af7-0000-7001-0000-000000000001 requests their bookings with status "pending_payment"
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 1 |
    And all bookings should have status:
      | pending_payment |

  Scenario: Booking list includes seat_positions for manual selection
    Given bookings exist:
      | buyer_id                             | event_id                             | total_price | status | paid_at | id                                   | section | subsection | quantity | seat_selection_mode | seat_positions        |
      | 019a1af7-0000-7001-0000-000000000001 | 019a1af7-0000-7003-0000-000000000001 |        1500 | paid   | null    | 019a1af7-0000-7004-0000-000000000005 | A       |          1 |        2 | manual              | ["A-1-1-5","A-1-1-6"] |
    When buyer with id 019a1af7-0000-7001-0000-000000000001 requests their bookings
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 4 |
    And the booking with id 019a1af7-0000-7004-0000-000000000005 should have seat_positions:
      | A-1-1-5 |
      | A-1-1-6 |

  Scenario: Get booking by ID with full details and tickets
    Given bookings with tickets exist:
      | buyer_id                             | event_id                             | total_price | status | paid_at  | booking_id                           | section | subsection | quantity | seat_selection_mode | ticket_ids                                                     |
      | 019a1af7-0000-7001-0000-000000000001 | 019a1af7-0000-7003-0000-000000000001 |        2000 | paid   | not_null | 019a1af7-0000-7004-0000-000000000006 | A       |          1 |        2 | best_available      | 019a1af7-0000-7005-0000-000000000065,019a1af7-0000-7005-0000-000000000066 |
    When buyer with id 019a1af7-0000-7001-0000-000000000001 requests booking details for booking 019a1af7-0000-7004-0000-000000000006
    Then the response status code should be:
      | 200 |
    And the booking details should include:
      | id                                   | event_name | venue_name   | section | subsection | quantity | total_price | status | seller_name  | buyer_name  |
      | 019a1af7-0000-7004-0000-000000000006 | Event A    | Taipei Arena | A       |          1 |        2 |        2000 | paid   | Test Seller1 | Test Buyer1 |
    And the booking should include tickets:
      | ticket_id                            | section | subsection | row | seat | price | status |
      | 019a1af7-0000-7005-0000-000000000065 | A       |          1 |   1 |    1 |  1000 | sold   |
      | 019a1af7-0000-7005-0000-000000000066 | A       |          1 |   1 |    2 |  1000 | sold   |
