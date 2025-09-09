Feature: Order Payment
  As a buyer
  I want to pay for my orders
  So that I can complete the purchase

  Scenario: Successfully pay for an order
    Given an order exists with status "pending_payment":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  1000 |
    When the buyer pays for the order with:
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be:
      | 200 |
    And the order status should be:
      | paid |
    And the order should have:
      | created_at | paid_at  |
      | not_null   | not_null |
    And the payment should have:
      | payment_id | status |
      | PAY_MOCK_* | paid   |
    And the product status should be:
      | sold |

  Scenario: Cannot pay for already paid order
    Given an order exists with status "paid":
      | buyer_id | seller_id | product_id | price | paid_at  |
      |        2 |         1 |          1 |  1000 | not_null |
    When the buyer tries to pay for the order again
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Order already paid |

  Scenario: Cannot pay for cancelled order
    Given an order exists with status "cancelled":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  1000 |
    When the buyer tries to pay for the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot pay for cancelled order |

  Scenario: Only buyer can pay for their order
    Given an order exists with status "pending_payment":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  1000 |
    When another user tries to pay for the order
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only the buyer can pay for this order |

  Scenario: Cancel unpaid order
    Given an order exists with status "pending_payment":
      | buyer_id | seller_id | product_id | price |
      |        2 |         1 |          1 |  1000 |
    When the buyer cancels the order
    Then the response status code should be:
      | 204 |
    And the order status should be:
      | cancelled |
    And the order should have:
      | created_at | paid_at |
      | not_null   | null    |
    And the product status should be:
      | available |

  Scenario: Cannot cancel paid order
    Given an order exists with status "paid":
      | buyer_id | seller_id | product_id | price | paid_at  |
      |        2 |         1 |          1 |  1000 | not_null |
    When the buyer tries to cancel the order
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot cancel paid order |
