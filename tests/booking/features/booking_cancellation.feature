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

  Scenario: Successfully cancel unpaid booking
    Given a event exists:
      | name         | description     | is_active | status    | seller_id | venue_name   | seating_config                                                                                                |
      | Rock Concert | For cancel test | true      | available |         1 | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        2000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer cancels the booking
    Then the response status code should be:
      | 200 |
    And the booking status should be:
      | cancelled |
    And the event status should be:
      | available |

  Scenario: Cannot cancel paid booking
    Given a event exists:
      | name          | description  | is_active | status   | seller_id | venue_name  | seating_config                                                                                                |
      | Jazz Festival | Already paid | true      | sold_out |         1 | Taipei Dome | {"sections": [{"name": "B", "price": 1200, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    And an booking exists with status "paid":
      | buyer_id | seller_id | event_id | total_price | paid_at  |
      |        2 |         1 |        1 |        3000 | not_null |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid booking |
    And the booking status should remain:
      | paid |

  Scenario: Cannot cancel already cancelled booking
    Given a event exists:
      | name        | description       | is_active | status    | seller_id | venue_name   | seating_config                                                                                             |
      | Opera Night | Already cancelled | true      | available |         1 | Taipei Arena | {"sections": [{"name": "A", "price": 800, "subsections": [{"number": 1, "rows": 1, "seats_per_row": 1}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And an booking exists with status "cancelled":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |         800 |
    When the buyer tries to cancel the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Booking already cancelled |

  Scenario: Only buyer can cancel their own booking
    Given a event exists:
      | name        | description         | is_active | status    | seller_id | venue_name  | seating_config                                                                                                |
      | Pop Concert | Not buyer's booking | true      | available |         1 | Taipei Dome | {"sections": [{"name": "D", "price": 1500, "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    And another buyer exists:
      | email            | password | name          | role  |
      | another@test.com | P@ssw0rd | Another Buyer | buyer |
    And an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        2500 |
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
    And the event status should remain:
      | available |

  Scenario: Seller cannot cancel buyer's booking
    Given a event exists:
      | name        | description    | is_active | status    | seller_id | venue_name   | seating_config                                                                                               |
      | Comedy Show | Seller's event | true      | available |         1 | Taipei Arena | {"sections": [{"name": "E", "price": 900, "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]} |
    And an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        4000 |
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
    And the event status should remain:
      | available |

  Scenario: Cannot cancel non-existent booking for available event
    Given a event exists:
      | name          | description     | is_active | status    | seller_id | venue_name  | seating_config                                                                                                |
      | Dance Concert | Available event | true      | available |         1 | Taipei Dome | {"sections": [{"name": "F", "price": 1100, "subsections": [{"number": 6, "rows": 30, "seats_per_row": 25}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel a non-existent booking
    Then the response status code should be:
      | 404 |
    And the error message should contain:
      | Booking not found |
    And the event status should remain:
      | available |

  Scenario: Buyer can cancel their own reservation
    Given a event exists:
      | name            | description     | is_active | status    | seller_id | venue_name   | seating_config                                                                                                |
      | Musical Theatre | For reservation | true      | available |         1 | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        3000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When buyer cancels reservation:
      | buyer_id | booking_id |
      |        2 |          1 |
    Then the response status code should be:
      | 200 |
    And reservation status should be:
      | status |
      | ok     |
    And tickets should return to available:
      | status    | count |
      | available |     3 |
