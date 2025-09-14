Feature: Order List
  As a buyer
  I want to list my bookings with details
  So that I can track my purchases

  As a seller
  I want to list bookings for my events
  So that I can track my sales

  Background:
    Given users exist:
      | email            | password | name         | role   | id |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |  1 |
      | seller2@test.com | P@ssw0rd | Test Seller2 | seller |  2 |
      | buyer1@test.com  | P@ssw0rd | Test Buyer1  | buyer  |  3 |
      | buyer2@test.com  | P@ssw0rd | Test Buyer2  | buyer  |  4 |
      | buyer3@test.com  | P@ssw0rd | Test Buyer3  | buyer  |  5 |
    And events exist:
      | name    | seller_id | status    | id | venue_name   | seating_config                                                                                 |
      | Event A |         1 | sold_out  |  1 | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
      | Event B |         1 | sold_out  |  2 | Taipei Dome  | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
      | Event C |         2 | sold_out  |  3 | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
      | Event D |         1 | available |  4 | Taipei Dome  | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    And bookings exist:
      | buyer_id | seller_id | event_id | total_price | status          | paid_at  | id |
      |        3 |         1 |        1 |        1000 | paid            | not_null |  1 |
      |        3 |         1 |        2 |        2000 | paid            | not_null |  2 |
      |        3 |         2 |        3 |        3000 | pending_payment | null     |  3 |
      |        4 |         1 |        4 |        4000 | cancelled       | null     |  4 |

  Scenario: Buyer lists their bookings
    When buyer with id 3 requests their bookings
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 3 |
    And the bookings should include:
      | id | event_name | total_price | status          | seller_name  | created_at | paid_at  |
      |  1 | Event A    |        1000 | paid            | Test Seller1 | not_null   | not_null |
      |  2 | Event B    |        2000 | paid            | Test Seller1 | not_null   | not_null |
      |  3 | Event C    |        3000 | pending_payment | Test Seller2 | not_null   | null     |

  Scenario: Seller lists bookings for their events
    When seller with id 1 requests their bookings
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 3 |
    And the bookings should include:
      | id | event_name | total_price | status    | buyer_name  | created_at | paid_at  |
      |  1 | Event A    |        1000 | paid      | Test Buyer1 | not_null   | not_null |
      |  2 | Event B    |        2000 | paid      | Test Buyer1 | not_null   | not_null |
      |  4 | Event D    |        4000 | cancelled | Test Buyer2 | not_null   | null     |

  Scenario: Buyer with no bookings gets empty list
    When buyer with id 5 requests their bookings
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 0 |

  Scenario: Filter bookings by status - paid bookings only
    When buyer with id 3 requests their bookings with status "paid"
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 2 |
    And all bookings should have status:
      | paid |

  Scenario: Filter bookings by status - pending payment only
    When buyer with id 3 requests their bookings with status "pending_payment"
    Then the response status code should be:
      | 200 |
    And the response should contain bookings:
      | 1 |
    And all bookings should have status:
      | pending_payment |
