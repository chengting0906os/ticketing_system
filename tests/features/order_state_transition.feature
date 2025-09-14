Feature: Order State Transition
  As a marketplace system
  I want to enforce proper order state transitions
  So that orders follow valid business workflows

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And tickets exist for event:
      | event_id | status    | price |
      |        1 | available |  1000 |

  Scenario: Cannot cancel PAID order
    Given an order exists with status "paid":
      | buyer_id | seller_id | event_id | total_price | paid_at  |
      |        2 |         1 |        1 |        2000 | not_null |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid order |

  Scenario: Cannot pay for CANCELLED order
    Given an order exists with status "cancelled":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        2000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to pay for the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot pay for cancelled order |

  Scenario: Cannot re-cancel CANCELLED order
    Given an order exists with status "cancelled":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        2000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Order already cancelled |

  Scenario: Valid state transition from PENDING_PAYMENT to PAID
    Given an order exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        2000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer pays for the order
    Then the response status code should be:
      | 200 |
    And the order status should be:
      | paid |

  Scenario: Valid state transition from PENDING_PAYMENT to CANCELLED
    Given an order exists with status "pending_payment":
      | buyer_id | seller_id | event_id | total_price |
      |        2 |         1 |        1 |        2000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer cancels the order
    Then the response status code should be:
      | 204 |
    And the order status should be:
      | cancelled |
