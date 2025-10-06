@integration
Feature: Booking Payment
  As a buyer
  I want to pay for my bookings
  So that I can complete the purchase

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And another buyer exists:
      | email            | password | name          | role  |
      | another@test.com | P@ssw0rd | Another Buyer | buyer |
    And an event exists:
      | name         | description | is_active | status    | seller_id | venue_name   | seating_config                                                                                                |
      | Test Concert | Test event  | true      | available |         1 | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |

  Scenario: Successfully pay for an booking
    Given a booking exists with status "pending_payment":
      | buyer_id | event_id | total_price |
      |        2 |        1 |        1000 |
    When the buyer pays for the booking with:
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be:
      | 200 |
    And the booking status should be:
      | paid |
    And the booking should have:
      | created_at | paid_at  |
      | not_null   | not_null |
    And the payment should have:
      | payment_id | status |
      | PAY_MOCK_* | paid   |

  Scenario: Cannot pay for already paid booking
    Given a booking exists with status "paid":
      | buyer_id | event_id | total_price | paid_at  |
      |        2 |        1 |        1000 | not_null |
    When the buyer tries to pay for the booking again
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Booking already paid |

  Scenario: Cannot pay for cancelled booking
    Given a booking exists with status "cancelled":
      | buyer_id | event_id | total_price |
      |        2 |        1 |        1000 |
    When the buyer tries to pay for the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot pay for cancelled booking |

  Scenario: Only buyer can pay for their booking
    Given a booking exists with status "pending_payment":
      | buyer_id | event_id | total_price |
      |        2 |        1 |        1000 |
    When another user tries to pay for the booking
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only the buyer can pay for this booking |

  Scenario: Cancel unpaid booking
    Given a booking exists with status "pending_payment":
      | buyer_id | event_id | total_price |
      |        2 |        1 |        1000 |
    When the buyer cancels the booking
    Then the response status code should be:
      | 200 |
    And the booking status should be:
      | cancelled |
    And the booking should have:
      | created_at | paid_at |
      | not_null   | null    |

  Scenario: Cannot cancel paid booking
    Given a booking exists with status "paid":
      | buyer_id | event_id | total_price | paid_at  |
      |        2 |        1 |        1000 | not_null |
    When the buyer tries to cancel the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid booking |
