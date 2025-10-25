@integration
Feature: Get Event with Seat Availability
  As a user
  I want to view event details with seat availability
  So that I can see which sections have available seats

  Background:
    Given a seller user exists
      | email           | password | name | role   |
      | seller@test.com | P@ssw0rd | Ryan | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |

  @smoke
  Scenario: Get event with seat availability for all subsections
    Given an event exists with seating config:
      | name         | description | venue_name   | seating_config                                                                                                                                                                                              |
      | Rock Concert | Great music | Taipei Arena | {"sections": [{"name": "A", "price": 3000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 10}, {"number": 2, "rows": 10, "seats_per_row": 10}]}, {"name": "B", "price": 2000, "subsections": [{"number": 1, "rows": 5, "seats_per_row": 8}]}]} |
    When I get the event details
    Then the response status code should be:
      | 200 |
    And the event response should include:
      | name         | venue_name   |
      | Rock Concert | Taipei Arena |
    And the seating config should include sections with availability:
      | section_name | subsection_number | available | total |
      | A            | 1                 | 100       | 100   |
      | A            | 2                 | 100       | 100   |
      | B            | 1                 | 40        | 40    |
    And the response should contain 240 tickets

  Scenario: Get event shows seat availability from Kvrocks
    Given an event exists with seating config:
      | name         | description | venue_name   | seating_config                                                                                               |
      | Rock Concert | Great music | Taipei Arena | {"sections": [{"name": "A", "price": 2000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 10}]}]} |
    When I get the event details
    Then the response status code should be:
      | 200 |
    And the seating config should include sections with availability:
      | section_name | subsection_number | available | total |
      | A            | 1                 | 100       | 100   |

  Scenario: Get event with detailed ticket information
    Given an event exists with seating config:
      | name         | description | venue_name   | seating_config                                                                                               |
      | Rock Concert | Great music | Taipei Arena | {"sections": [{"name": "A", "price": 2000, "subsections": [{"number": 1, "rows": 2, "seats_per_row": 3}]}]} |
    When I get the event details
    Then the response status code should be:
      | 200 |
    And the response should contain 6 tickets
    And the tickets should include seat identifiers:
      | A-1-1-1 |
      | A-1-1-2 |
      | A-1-1-3 |
      | A-1-2-1 |
      | A-1-2-2 |
      | A-1-2-3 |
    And all tickets should have status "available"

  Scenario: Get non-existent event
    When I get event with id 99999
    Then the response status code should be:
      | 404 |
    And the error message should contain:
      | Event with id 00000000-0000-0000-0000-000000099999 not found |
