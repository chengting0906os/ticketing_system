Feature: Product Creation
  As a seller
  I want to create new products
  So that buyers can purchase them

  Background:
    Given a seller user exists
      | email           | password | name | role   |
      | seller@test.com | P@ssw0rd | Ryan | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |

  Scenario: Create a new product successfully
    When I create a product with
      | name      | description             | price |
      | iPhone 18 | Latest Apple smartphone |  1500 |
    Then the product should be created with
      | id        | seller_id | name      | description             | price | is_active |
      | {any_int} | {any_int} | iPhone 18 | Latest Apple smartphone |  1500 | true      |
    And the response status code should be:
      | 201 |

  Scenario: Create product with negative price
    When I create a product with
      | name      | description | price |
      | iPhone 25 | Apple phone |  -500 |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |

  Scenario: Create inactive product
    When I create a product with
      | name     | description         | price | is_active |
      | iPad Pro | Professional tablet |  2000 | false     |
    Then the product should be created with
      | id        | seller_id | name     | description         | price | is_active | status    |
      | {any_int} | {any_int} | iPad Pro | Professional tablet |  2000 | false     | available |
    And the response status code should be:
      | 201 |

  Scenario: Buyer cannot create product
    Given a buyer user exists
      | email          | password | name  | role  |
      | buyer@test.com | P@ssw0rd | Alice | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When I create a product with
      | name    | description  | price |
      | MacBook | Apple laptop |  3000 |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |
