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
      | email            | password | name         | role   | id |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller | 4  |
      | seller2@test.com | P@ssw0rd | Test Seller2 | seller | 5  |
      | buyer1@test.com  | P@ssw0rd | Test Buyer1  | buyer  | 6  |
      | buyer2@test.com  | P@ssw0rd | Test Buyer2  | buyer  | 7  |
      | buyer3@test.com  | P@ssw0rd | Test Buyer3  | buyer  | 8  |
    And events exist:
      | name    | seller_id | status    | id | venue_name   | seating_config                                                                         |
      | Event A | 4         | sold_out  | 1  | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
      | Event B | 4         | sold_out  | 2  | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 2000, "subsections": 1}]} |
      | Event C | 5         | sold_out  | 3  | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "C", "price": 3000, "subsections": 1}]} |
      | Event D | 4         | available | 4  | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 4000, "subsections": 1}]} |
    And bookings exist:
      | buyer_id | event_id | total_price | status          | paid_at  | id |
      | 6        | 1        | 1000        | paid            | not_null | 1  |
      | 6        | 2        | 2000        | paid            | not_null | 2  |
      | 6        | 3        | 3000        | pending_payment | null     | 3  |
      | 7        | 4        | 4000        | cancelled       | null     | 4  |

  @smoke
  Scenario: Buyer lists their bookings
    When buyer with id 6 requests their bookings
    Then the response status code should be 200
    And the response should have 3 items
    And the bookings should include:
      | id | event_name | total_price | status          | seller_name  | venue_name   | section | subsection | quantity | seat_selection_mode | created_at | paid_at  |
      | 1  | Event A    | 1000        | paid            | Test Seller1 | Taipei Arena | A       | 1          | 1        | best_available      | not_null   | not_null |
      | 2  | Event B    | 2000        | paid            | Test Seller1 | Taipei Dome  | B       | 1          | 1        | best_available      | not_null   | not_null |
      | 3  | Event C    | 3000        | pending_payment | Test Seller2 | Taipei Arena | C       | 1          | 1        | best_available      | not_null   | null     |

  Scenario: Seller lists bookings for their events
    When seller with id 4 requests their bookings
    Then the response status code should be 200
    And the response should have 3 items
    And the bookings should include:
      | id | event_name | total_price | status    | buyer_name  | venue_name   | section | subsection | quantity | seat_selection_mode | created_at | paid_at  |
      | 1  | Event A    | 1000        | paid      | Test Buyer1 | Taipei Arena | A       | 1          | 1        | best_available      | not_null   | not_null |
      | 2  | Event B    | 2000        | paid      | Test Buyer1 | Taipei Dome  | B       | 1          | 1        | best_available      | not_null   | not_null |
      | 4  | Event D    | 4000        | cancelled | Test Buyer2 | Taipei Dome  | D       | 1          | 1        | best_available      | not_null   | null     |

  Scenario: Buyer with no bookings gets empty list
    When buyer with id 8 requests their bookings
    Then the response status code should be 200
    And the response should have 0 items

  Scenario: Filter bookings by status - paid bookings only
    When buyer with id 6 requests their bookings with status "paid"
    Then the response status code should be 200
    And the response should have 2 items
    And all bookings should have status:
      | paid |

  Scenario: Filter bookings by status - pending payment only
    When buyer with id 6 requests their bookings with status "pending_payment"
    Then the response status code should be 200
    And the response should have 1 items
    And all bookings should have status:
      | pending_payment |

  Scenario: Booking list includes seat_positions for manual selection
    Given bookings exist:
      | buyer_id | event_id | total_price | status | paid_at | id | section | subsection | quantity | seat_selection_mode | seat_positions        |
      | 6        | 1        | 1500        | paid   | null    | 5  | A       | 1          | 2        | manual              | ["1-5","1-6"] |
    When buyer with id 6 requests their bookings
    Then the response status code should be 200
    And the response should have 4 items
    And the booking with id 5 should have seat_positions:
      | 1-5 |
      | 1-6 |

  Scenario: Get booking by ID with full details and tickets
    Given bookings exist:
      | buyer_id | event_id | total_price | status | paid_at  | id | section | subsection | quantity | seat_selection_mode |
      | 6        | 1        | 2000        | paid   | not_null | 6  | A       | 1          | 2        | best_available      |
    When buyer with id 6 requests booking details for booking 6
    Then the response status code should be 200
    And the booking details should include:
      | id | event_name | venue_name   | section | subsection | quantity | total_price | status | seller_name  | buyer_name  |
      | 6  | Event A    | Taipei Arena | A       | 1          | 2        | 2000        | paid   | Test Seller1 | Test Buyer1 |
    And the booking should include 2 tickets with:
      | section | subsection | price | status |
      | A       | 1          | 1000  | sold   |
