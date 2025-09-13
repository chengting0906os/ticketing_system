Feature: Event Creation
  As a seller
  I want to create new events
  So that buyers can purchase them

  Background:
    Given a seller user exists
      | email           | password | name | role   |
      | seller@test.com | P@ssw0rd | Ryan | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |

  Scenario: Create a new event successfully
    When I create a event with
      | name      | description             | price | venue_name   | seating_config                                                                                 |
      | iPhone 18 | Latest Apple smartphone |  1500 | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    Then the event should be created with
      | id        | seller_id | name      | description             | price | is_active | venue_name   | seating_config                                                                                 |
      | {any_int} | {any_int} | iPhone 18 | Latest Apple smartphone |  1500 | true      | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And the response status code should be:
      | 201 |

  Scenario: Create event with negative price
    When I create a event with
      | name      | description | price | venue_name   | seating_config                                                                                 |
      | iPhone 25 | Apple phone |  -500 | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |

  Scenario: Create inactive event
    When I create a event with
      | name     | description         | price | is_active | venue_name  | seating_config                                                                                 |
      | iPad Pro | Professional tablet |  2000 | false     | Taipei Dome | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    Then the event should be created with
      | id        | seller_id | name     | description         | price | is_active | status    | venue_name  | seating_config                                                                                 |
      | {any_int} | {any_int} | iPad Pro | Professional tablet |  2000 | false     | available | Taipei Dome | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    And the response status code should be:
      | 201 |

  Scenario: Buyer cannot create event
    Given a buyer user exists
      | email          | password | name  | role  |
      | buyer@test.com | P@ssw0rd | Alice | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When I create a event with
      | name    | description  | price | venue_name   | seating_config                                                                                 |
      | MacBook | Apple laptop |  3000 | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |
