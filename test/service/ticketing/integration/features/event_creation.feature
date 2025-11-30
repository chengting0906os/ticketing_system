@integration
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

  @smoke
  Scenario: Create a new event successfully
    When I create a event with
      | name         | description                  | venue_name   | seating_config                                                               |
      | Rock Concert | Amazing live rock music show | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    Then the event should be created with:
      | id        | seller_id | name         | description                  | is_active | venue_name   | seating_config                                                               |
      | {any_int} | {any_int} | Rock Concert | Amazing live rock music show | true      | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And the response status code should be:
      | 201 |

  Scenario: Create event with empty name
    When I create a event with
      | name | description         | venue_name   | seating_config                                                               |
      |      | Jazz music festival | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Event name cannot be empty |

  Scenario: Create inactive event
    When I create a event with
      | name             | description                 | is_active | venue_name  | seating_config                                                               |
      | Broadway Musical | Classic theater performance | false     | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1500, "subsections": 1}]} |
    Then the event should be created with:
      | id        | seller_id | name             | description                 | is_active | status    | venue_name  | seating_config                                                               |
      | {any_int} | {any_int} | Broadway Musical | Classic theater performance | false     | available | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1500, "subsections": 1}]} |
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
      | name        | description           | venue_name   | seating_config                                                               |
      | Comedy Show | Stand-up comedy night | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |

  Scenario: Seller creates event with seating config and tickets are auto-created
    When seller creates event with seating config:
      | name       | description   | venue_name   | seating_config                                                              |
      | Test Event | Great concert | Taipei Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    Then the response status code should be:
      | 201 |
    And the event should be created with:
      | name       | status    | is_active |
      | Test Event | available | true      |
    And tickets should be auto-created with:
      | count | price | status    |
      |    50 |  1000 | available |

  Scenario: Cannot create event without valid seating config
    When seller creates event with invalid seating config:
      | name       | description | venue_name   | seating_config |
      | Test Event | Bad config  | Taipei Arena | invalid_json   |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Input should be a valid dictionary |

  Scenario: Seller creates event with multiple sections and subsections
    When seller creates event with complex seating config:
      | name        | description   | venue_name  | seating_config                                                                                                     |
      | Big Concert | Multi-section | Taipei Dome | {"rows": 10, "cols": 20, "sections": [{"name": "A", "price": 1500, "subsections": 1}, {"name": "B", "price": 1200, "subsections": 2}]} |
    Then the response status code should be:
      | 201 |
    And tickets should be auto-created with:
      | count | status    |
      |   600 | available |

  Scenario: Buyer cannot create events
    Given a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When buyer tries to create event with seating config:
      | name       | description  | venue_name   | seating_config                                                              |
      | Test Event | Unauthorized | Taipei Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |

  Scenario: Cannot create event with negative ticket price
    When seller creates event with negative ticket price:
      | name       | description | venue_name   | seating_config                                                              |
      | Test Event | Bad price   | Taipei Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": -500, "subsections": 1}]} |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Ticket price must over 0 |

  @compensating_transaction
  Scenario: Compensating transaction when Kvrocks initialization fails
    Given Kvrocks seat initialization will fail
    When I create a event with
      | name         | description                       | venue_name   | seating_config                                                               |
      | Doomed Event | This event will fail Kvrocks init | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    Then the response status code should be:
      | 500 |
    And the error message should contain:
      | Internal server error |
    And the event should not exist in database:
      | name         |
      | Doomed Event |
    And no tickets should exist for this event
    And the database should be in consistent state
