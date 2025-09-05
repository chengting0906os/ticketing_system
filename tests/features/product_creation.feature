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
      | name      | description             | price |
      | iPhone 18 | Latest Apple smartphone |  1500 |
    Then the product should be created with
      | name      | description             | price |
      | iPhone 18 | Latest Apple smartphone |  1500 |
    And get 201

  Scenario: Create product with negative price
    When I create a product with
      | name      | description | price |
      | iPhone 25 | Apple phone |  -500 |
    Then get 400
    And the error message should contain "Price must be positive"
