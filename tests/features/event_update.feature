Feature: Event Update
  As a seller
  I want to update my events
  So that I can manage my inventory

  Background:
    Given a seller user exists
      | email           | password | name | role   |
      | seller@test.com | P@ssw0rd | Ryan | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    And a event exists
      | seller_id | name      | description             | price | is_active |
      |         1 | iPhone 18 | Latest Apple smartphone |  1500 | true      |

  Scenario: Deactivate a event
    When I update the event to
      | is_active |
      | false     |
    Then the event should be updated with
      | id        | seller_id | name      | description             | price | is_active | status    |
      | {any_int} |         1 | iPhone 18 | Latest Apple smartphone |  1500 | false     | available |
    And the response status code should be:
      | 200 |

  Scenario: Update event price
    When I update the event to
      | price |
      |  1299 |
    Then the event should be updated with
      | id        | seller_id | name      | description             | price | is_active | status    |
      | {any_int} |         1 | iPhone 18 | Latest Apple smartphone |  1299 | true      | available |
    And the response status code should be:
      | 200 |

  Scenario: Update event with negative price should fail
    When I update the event to
      | price |
      |  -100 |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |
