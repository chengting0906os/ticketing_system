Feature: Product Update
  As a seller
  I want to update my products
  So that I can manage my inventory

  Background:
    Given a seller user exists
      | email           | password    | name | role   |
      | seller@test.com | Test123456! | Ryan | seller |
    And a product exists
      | seller_id | name      | description             | price | is_active |
      | 1         | iPhone 18 | Latest Apple smartphone |  1500 | true      |

  Scenario: Deactivate a product
    When I update the product to
      | is_active |
      | false     |
    Then the product should be updated with
      | id        | seller_id | name      | description             | price | is_active | status    |
      | {any_int} | 1         | iPhone 18 | Latest Apple smartphone |  1500 | false     | available |
    And get 200

  Scenario: Update product price
    When I update the product to
      | price |
      | 1299  |
    Then the product should be updated with
      | id        | seller_id | name      | description             | price | is_active | status    |
      | {any_int} | 1         | iPhone 18 | Latest Apple smartphone |  1299 | true      | available |
    And get 200

  Scenario: Update product with negative price should fail
    When I update the product to
      | price |
      | -100  |
    Then get 400
    And the error message should contain "Price must be positive"
