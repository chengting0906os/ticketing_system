Feature: Order Price Validation
  As a marketplace system
  I want to validate order prices properly
  So that orders maintain data integrity and business rules

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |

  Scenario: Cannot create order with negative price product
    Given a product exists with negative price:
      | name         | description      | price | seller_id | is_active | status    |
      | Test Product | Test Description |  -100 |         1 | true      | available |
    When the buyer tries to create an order for the negative price product
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |

  Scenario: Cannot create order with zero price product
    Given a product exists with zero price:
      | name         | description      | price | seller_id | is_active | status    |
      | Free Product | Test Description |     0 |         1 | true      | available |
    When the buyer tries to create an order for the zero price product
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |

  Scenario: Order price matches product price at creation time
    Given a product exists:
      | name         | description      | price | seller_id | is_active | status    |
      | Test Product | Test Description |  1000 |         1 | true      | available |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer creates an order for the product
    Then the order should be created with:
      | price | status          |
      |  1000 | pending_payment |
    And the order price should be 1000

  Scenario: Product price changes do not affect existing orders
    Given a product exists:
      | name         | description      | price | seller_id | is_active | status    |
      | Test Product | Test Description |  1000 |         1 | true      | available |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    When the product price is updated to 2000
    Then the existing order price should remain 1000
    And the product status should be "reserved"

  Scenario: New orders use updated product price
    Given a product exists:
      | name         | description      | price | seller_id | is_active | status    |
      | Test Product | Test Description |  1000 |         1 | true      | available |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    And the product price is updated to 2000
    And the buyer cancels the order to release the product
    When another buyer creates an order for the same product
    Then the new order should have price 2000

  Scenario: Paid order price remains unchanged after product price update
    Given a product exists:
      | name         | description      | price | seller_id | is_active | status    |
      | Test Product | Test Description |  1500 |         1 | true      | available |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the product
    And the buyer pays for the order
    When the product price is updated to 3000
    Then the paid order price should remain 1500
    And the order status should remain "paid"
