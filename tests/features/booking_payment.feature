Feature: Booking Payment
  As a buyer
  I want to pay for my bookings
  So that I can complete the purchase

  Scenario: Successfully pay for an booking
    Given an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        1000 |
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
    And the event status should be:
      | sold_out |
    And the tickets should have status:
      | status |
      | sold   |

  Scenario: Cannot pay for already paid booking
    Given an booking exists with status "paid":
      | buyer_id | seller_id | event_id | total_price | paid_at  |
      |        2 |         1 |        1 |        1000 | not_null |
    When the buyer tries to pay for the booking again
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Booking already paid |

  Scenario: Cannot pay for cancelled booking
    Given an booking exists with status "cancelled":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        1000 |
    When the buyer tries to pay for the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot pay for cancelled booking |

  Scenario: Only buyer can pay for their booking
    Given an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        1000 |
    When another user tries to pay for the booking
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only the buyer can pay for this booking |

  Scenario: Cancel unpaid booking
    Given an booking exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        1000 |
    When the buyer cancels the booking
    Then the response status code should be:
      | 200 |
    And the booking status should be:
      | cancelled |
    And the booking should have:
      | created_at | paid_at |
      | not_null   | null    |
    And the event status should be:
      | available |
    And the tickets should have status:
      | status    |
      | available |

  Scenario: Cannot cancel paid booking
    Given an booking exists with status "paid":
      | buyer_id | seller_id | event_id | total_price | paid_at  |
      |        2 |         1 |        1 |        1000 | not_null |
    When the buyer tries to cancel the booking
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid booking |
