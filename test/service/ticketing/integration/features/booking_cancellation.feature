@integration
Feature: Booking Cancellation
  As a buyer
  I want to cancel my unpaid bookings
  So that I can release events I no longer want to purchase

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |

  @smoke
  Scenario: Successfully cancel unpaid booking
    Given an event exists:
      | name         | description     | is_active | status    | seller_id | venue_name   | seating_config                                                               |
      | Rock Concert | For cancel test | true      | available | 1         | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And a booking exists with status "pending_payment":
      | buyer_id | event_id | total_price |
      | 2        | 1        | 2000        |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer cancels the booking
    Then the response status code should be:
      | 200 |
    And the booking status should be:
      | cancelled |

  Scenario: Cannot cancel completed booking
    Given an event exists:
      | name          | description  | is_active | status   | seller_id | venue_name  | seating_config                                                               |
      | Jazz Festival | Already paid | true      | sold_out | 1         | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1200, "subsections": 1}]} |
    And a booking exists with status "completed":
      | buyer_id | event_id | total_price | paid_at  |
      | 2        | 1        | 3000        | not_null |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel completed booking |
    And the booking status should remain:
      | completed |

  Scenario: Cannot cancel already cancelled booking
    Given an event exists:
      | name        | description       | is_active | status    | seller_id | venue_name   | seating_config                                                           |
      | Opera Night | Already cancelled | true      | available | 1         | Taipei Arena | {"rows": 1, "cols": 1, "sections": [{"name": "A", "price": 800, "subsections": 1}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And a booking exists with status "cancelled":
      | buyer_id | event_id | total_price |
      | 2        | 1        | 800         |
    When the buyer tries to cancel the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Booking already cancelled |

  Scenario: Only buyer can cancel their own booking
    Given an event exists:
      | name        | description         | is_active | status    | seller_id | venue_name  | seating_config                                                               |
      | Pop Concert | Not buyer's booking | true      | available | 1         | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 1500, "subsections": 1}]} |
    And another buyer exists:
      | email            | password | name          | role  |
      | another@test.com | P@ssw0rd | Another Buyer | buyer |
    And a booking exists with status "pending_payment":
      | buyer_id | event_id | total_price |
      | 2        | 1        | 2500        |
    And I am logged in as:
      | email            | password |
      | another@test.com | P@ssw0rd |
    When the user tries to cancel someone else's booking
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only the buyer can cancel this booking |
    And the booking status should remain:
      | pending_payment |

  Scenario: Seller cannot cancel buyer's booking
    Given an event exists:
      | name        | description    | is_active | status    | seller_id | venue_name   | seating_config                                                              |
      | Comedy Show | Seller's event | true      | available | 1         | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "E", "price": 900, "subsections": 1}]} |
    And a booking exists with status "pending_payment":
      | buyer_id | event_id | total_price |
      | 2        | 1        | 4000        |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When the seller tries to cancel the buyer's booking
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only buyers can perform this action |
    And the booking status should remain:
      | pending_payment |

  Scenario: Cannot cancel non-existent booking for available event
    Given an event exists:
      | name          | description     | is_active | status    | seller_id | venue_name  | seating_config                                                               |
      | Dance Concert | Available event | true      | available | 1         | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "F", "price": 1100, "subsections": 1}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel a non-existent booking
    Then the response status code should be:
      | 404 |
    And the error message should contain:
      | Booking not found |
