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
    And a product exists:
      | name         | description      | price | seller_id | is_active | status    |
      | Test Product | Test Description |  1000 |         1 | true      | available |

  Scenario: Cannot cancel PAID order
    Given I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    And the buyer pays for the order
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid order |

  Scenario: Cannot pay for CANCELLED order
    Given I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    And the buyer cancels the order
    When the buyer tries to pay for the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot pay for cancelled order |

  Scenario: Cannot re-cancel CANCELLED order
    Given I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    And the buyer cancels the order
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Order already cancelled |

  Scenario: Valid state transition from PENDING_PAYMENT to PAID
    Given I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    When the buyer pays for the order
    Then the response status code should be:
      | 200 |
    And the order status should be:
      | paid |

  Scenario: Valid state transition from PENDING_PAYMENT to CANCELLED
    Given I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    When the buyer cancels the order
    Then the response status code should be:
      | 204 |
    And the order status should be:
      | cancelled |
