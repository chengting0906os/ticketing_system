Feature: Order List
  As a buyer
  I want to list my orders with details
  So that I can track my purchases

  As a seller
  I want to list orders for my products
  So that I can track my sales

  Background:
    Given users exist:
      | email            | password | name         | role   | id |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |  1 |
      | seller2@test.com | P@ssw0rd | Test Seller2 | seller |  2 |
      | buyer1@test.com  | P@ssw0rd | Test Buyer1  | buyer  |  3 |
      | buyer2@test.com  | P@ssw0rd | Test Buyer2  | buyer  |  4 |
      | buyer3@test.com  | P@ssw0rd | Test Buyer3  | buyer  |  5 |
    And products exist:
      | name      | price | seller_id | status    | id |
      | Product A |  1000 |         1 | sold      |  1 |
      | Product B |  2000 |         1 | sold      |  2 |
      | Product C |  3000 |         2 | sold      |  3 |
      | Product D |  4000 |         1 | available |  4 |
    And orders exist:
      | buyer_id | seller_id | product_id | price | status          | paid_at  | id |
      |        3 |         1 |          1 |  1000 | paid            | not_null |  1 |
      |        3 |         1 |          2 |  2000 | paid            | not_null |  2 |
      |        3 |         2 |          3 |  3000 | pending_payment | null     |  3 |
      |        4 |         1 |          4 |  4000 | cancelled       | null     |  4 |

  Scenario: Buyer lists their orders
    When buyer with id 3 requests their orders
    Then the response status code should be:
      | 200 |
    And the response should contain orders:
      | 3 |
    And the orders should include:
      | id | product_name | price | status          | seller_name  | created_at | paid_at  |
      |  1 | Product A    |  1000 | paid            | Test Seller1 | not_null   | not_null |
      |  2 | Product B    |  2000 | paid            | Test Seller1 | not_null   | not_null |
      |  3 | Product C    |  3000 | pending_payment | Test Seller2 | not_null   | null     |

  Scenario: Seller lists orders for their products
    When seller with id 1 requests their orders
    Then the response status code should be:
      | 200 |
    And the response should contain orders:
      | 3 |
    And the orders should include:
      | id | product_name | price | status    | buyer_name  | created_at | paid_at  |
      |  1 | Product A    |  1000 | paid      | Test Buyer1 | not_null   | not_null |
      |  2 | Product B    |  2000 | paid      | Test Buyer1 | not_null   | not_null |
      |  4 | Product D    |  4000 | cancelled | Test Buyer2 | not_null   | null     |

  Scenario: Buyer with no orders gets empty list
    When buyer with id 5 requests their orders
    Then the response status code should be:
      | 200 |
    And the response should contain orders:
      | 0 |

  Scenario: Filter orders by status - paid orders only
    When buyer with id 3 requests their orders with status "paid"
    Then the response status code should be:
      | 200 |
    And the response should contain orders:
      | 2 |
    And all orders should have status:
      | paid |

  Scenario: Filter orders by status - pending payment only
    When buyer with id 3 requests their orders with status "pending_payment"
    Then the response status code should be:
      | 200 |
    And the response should contain orders:
      | 1 |
    And all orders should have status:
      | pending_payment |
