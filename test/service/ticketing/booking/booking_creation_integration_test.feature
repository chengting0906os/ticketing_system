@integration
Feature: Booking with Seat Selection
  As a buyer
  I want to select specific seats or get best available seats when creating a booking
  So that I can choose my preferred seating arrangements

  Background:
    Given I am logged in as a seller
    And an event exists with:
      | name         | description | is_active | status    | seller_id | venue_name   | seating_config                                                                        |
      | Test Concert | Test event  | true      | available | 1         | Taipei Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And I am logged in as a buyer

  @smoke
  Scenario: Manual seat selection - happy path
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | manual              | ["1-1","1-2"]  | 2        |
    Then the response status code should be 202
    And the response data should include:
      | buyer_id | status     |
      | 2        | processing |

  Scenario: Best available seat selection - happy path
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | best_available      | []             | 3        |
    Then the response status code should be 202
    And the response data should include:
      | buyer_id | status     |
      | 2        | processing |

  Scenario: Best available seat selection - single seat
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | best_available      | []             | 1        |
    Then the response status code should be 202
    And the response data should include:
      | buyer_id | status     |
      | 2        | processing |

  Scenario: Cannot select more than 4 tickets
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions                  | quantity |
      | {event_id} | A       | 1          | manual              | ["1-1","1-2","1-3","1-4","2-1"] | 5        |
    Then the response status code should be 400
    And the error message should contain "Maximum 4 tickets per booking"

  Scenario: Manual seat selection - single seat
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | manual              | ["2-3"]        | 1        |
    Then the response status code should be 202
    And the response data should include:
      | buyer_id | status     |
      | 2        | processing |

  Scenario: Booking accepted when requesting more seats than available (async validation)
    Given I am logged in as a seller
    And an event exists with:
      | name        | description | is_active | status    | seller_id | venue_name | seating_config                                                                      |
      | Small Event | Test event  | true      | available | 1         | Small Hall | {"rows": 1, "cols": 2, "sections": [{"name": "B", "price": 500, "subsections": 1}]} |
    And I am logged in as a buyer
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | B       | 1          | best_available      | []             | 4        |
    Then the response status code should be 202
    And the response data should include:
      | buyer_id | status     |
      | 2        | processing |

  Scenario: Manual selection with mismatched seat_positions count
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | manual              | ["1-1","1-2"]  | 3        |
    Then the response status code should be 400
    And the error message should contain "quantity must match the number of selected seat positions"

  Scenario: Best available with non-empty seat_positions
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | best_available      | ["1-1"]        | 1        |
    Then the response status code should be 400
    And the error message should contain "seat_positions must be empty for best_available"
