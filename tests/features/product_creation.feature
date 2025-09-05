Feature: Product Creation
  As a seller
  I want to create new products
  So that buyers can purchase them

  Background:
    Given a seller user exists
      | email           | password    | name | role   |
      | seller@test.com | Test123456! | Ryan | seller |

  Scenario: Create a new product successfully
    When I create a product with
      | seller_id | name      | description             | price |
      | 1         | iPhone 18 | Latest Apple smartphone |  1500 |
    Then the product should be created with
      | id        | seller_id | name      | description             | price | is_active |
      | {any_int} | 1         | iPhone 18 | Latest Apple smartphone |  1500 | true      |
    And get 201

  Scenario: Create product with negative price
    When I create a product with
      | seller_id | name      | description | price |
      | 1         | iPhone 25 | Apple phone |  -500 |
    Then get 400
    And the error message should contain "Price must be positive"

  Scenario: Create inactive product
    When I create a product with
      | seller_id | name     | description         | price | is_active |
      | 1         | iPad Pro | Professional tablet |  2000 | false     |
    Then the product should be created with
      | id        | seller_id | name     | description         | price | is_active | status    |
      | {any_int} | 1         | iPad Pro | Professional tablet |  2000 | false     | available |
    And get 201
