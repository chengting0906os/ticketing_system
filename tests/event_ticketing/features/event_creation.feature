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
      | name           | description                     | venue_name   | seating_config                                                                                                        |
      | Rock Concert   | Amazing live rock music show    | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    Then the event should be created with:
      | id        | seller_id | name           | description                     | is_active | venue_name   | seating_config                                                                                                        |
      | {any_int} | {any_int} | Rock Concert   | Amazing live rock music show    | true      | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And the response status code should be:
      | 201 |

  Scenario: Create event with empty name
    When I create a event with
      | name | description          | venue_name   | seating_config                                                                                                        |
      |      | Jazz music festival  | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Event name is required |

  Scenario: Create inactive event
    When I create a event with
      | name            | description                      | is_active | venue_name  | seating_config                                                                                                        |
      | Broadway Musical| Classic theater performance      | false     | Taipei Dome | {"sections": [{"name": "B", "price": 1500, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    Then the event should be created with:
      | id        | seller_id | name            | description                      | is_active | status    | venue_name  | seating_config                                                                                                        |
      | {any_int} | {any_int} | Broadway Musical| Classic theater performance      | false     | available | Taipei Dome | {"sections": [{"name": "B", "price": 1500, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
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
      | name         | description             | venue_name   | seating_config                                                                                                        |
      | Comedy Show  | Stand-up comedy night   | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |
