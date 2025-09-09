Feature: Product Deletion
  As a seller
  I want to delete my products when != reserved

  Scenario: Delete an available product
    Given a product exists with:
      | seller_id | name      | description    | price | is_active | status    |
      |         1 | Test Item | Item to delete |  1000 | true      | available |
    When I delete the product
    Then the response status code should be:
      | 204 |
    And the product should not exist

  Scenario: Cannot delete a reserved product
    Given a product exists with:
      | seller_id | name      | description   | price | is_active | status   |
      |         1 | Test Item | Reserved item |  1000 | true      | reserved |
    When I try to delete the product
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot delete reserved product |

  Scenario: Cannot delete a sold product
    Given a product exists with:
      | seller_id | name      | description | price | is_active | status |
      |         1 | Test Item | Sold item   |  1000 | true      | sold   |
    When I try to delete the product
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot delete sold product |
