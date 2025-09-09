Feature: Order Cancellation
  As a buyer
  I want to cancel my unpaid orders
  So that I can release products I no longer want to purchase

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |

  Scenario: Successfully cancel unpaid order
    Given a product exists:
      | name         | description     | price | is_active | status    | seller_id |
      | Test Product | For cancel test |  2000 | true      | available |         1 |
    And an order exists with status "pending_payment":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  2000 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer cancels the order
    Then the response status code should be:
      | 204 |
    And the order status should be:
      | cancelled |
    And the product status should be:
      | available |

  Scenario: Cannot cancel paid order
    Given a product exists:
      | name         | description  | price | is_active | status | seller_id |
      | Test Product | Already paid |  3000 | true      | sold   |         1 |
    And an order exists with status "paid":
      | buyer_id | seller_id | product_id | price | paid_at  |
      |        2 |         1 |          1 |  3000 | not_null |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid order |
    And the order status should remain:
      | paid |
    And the product status should remain:
      | sold |

  Scenario: Cannot cancel already cancelled order
    Given a product exists:
      | name         | description       | price | is_active | status    | seller_id |
      | Test Product | Already cancelled |  1500 | true      | available |         1 |
    And an order exists with status "cancelled":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  1500 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Order already cancelled |

  Scenario: Only buyer can cancel their own order
    Given a product exists:
      | name         | description       | price | is_active | status   | seller_id |
      | Test Product | Not buyer's order |  2500 | true      | reserved |         1 |
    And another buyer exists:
      | email            | password | name          | role  |
      | another@test.com | P@ssw0rd | Another Buyer | buyer |
    And an order exists with status "pending_payment":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  2500 |
    And I am logged in as:
      | email            | password |
      | another@test.com | P@ssw0rd |
    When the user tries to cancel someone else's order
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only the buyer can cancel this order |
    And the order status should remain:
      | pending_payment |
    And the product status should remain:
      | reserved |

  Scenario: Seller cannot cancel buyer's order
    Given a product exists:
      | name         | description      | price | is_active | status   | seller_id |
      | Test Product | Seller's product |  4000 | true      | reserved |         1 |
    And an order exists with status "pending_payment":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  4000 |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When the seller tries to cancel the buyer's order
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only buyers can perform this action |
    And the order status should remain:
      | pending_payment |
    And the product status should remain:
      | reserved |

  Scenario: Cannot cancel non-existent order for available product
    Given a product exists:
      | name         | description       | price | is_active | status    | seller_id |
      | Test Product | Available product |  1800 | true      | available |         1 |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to cancel a non-existent order
    Then the response status code should be:
      | 404 |
    And the error message should contain:
      | Order not found |
    And the product status should remain:
      | available |
