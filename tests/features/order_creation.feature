Feature: Order Creation
  As a buyer
  I want to create orders for available products
  So that I can purchase items

  Scenario: Successfully create order for available product
    Given a seller with a product:
      | name         | description    | price | is_active | status    |
      | Test Product | For order test |  1000 | true      | available |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer creates an order for the product
    Then the response status code should be:
      | 201 |
    And the order should be created with:
      | price | status          | created_at | paid_at |
      |  1000 | pending_payment | not_null   | null    |
    And the product status should be:
      | reserved |

  Scenario: Cannot create order for reserved product
    Given a seller with a product:
      | name         | description      | price | is_active | status   |
      | Test Product | Already reserved |  1000 | true      | reserved |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to create an order for the product
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Product not available |

  Scenario: Cannot create order for inactive product
    Given a seller with a product:
      | name         | description      | price | is_active | status    |
      | Test Product | Inactive product |  1000 | false     | available |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to create an order for the product
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Product not active |

  Scenario: Seller cannot create order
    Given a seller with a product:
      | name         | description    | price | is_active | status    |
      | Test Product | For order test |  1000 | true      | available |
    And a seller user exists
      | email           | password | name   | role   |
      | seller@test.com | P@ssw0rd | Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When the seller tries to create an order for their own product
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only buyers can perform this action |
