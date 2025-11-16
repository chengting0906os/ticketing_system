@integration
Feature: Booking with Seat Selection
  As a buyer
  I want to select specific seats or get best available seats when creating a booking
  So that I can choose my preferred seating arrangements

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And an event exists with seating configuration:
      | name         | venue_name   | seating_config                                                                                               |
      | Test Concert | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 5, "seats_per_row": 10}]}]} |

  @smoke
  Scenario: Manual seat selection - happy path
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | seat_positions |
      | manual              | 1-1,1-2        |
    Then the response status code should be:
      | 201 |
    And the booking status should be:
      | processing |

  Scenario: Best available seat selection - happy path
    When buyer creates booking with best available seat selection:
      | seat_selection_mode | quantity |
      | best_available      |        3 |
    Then the response status code should be:
      | 201 |
    And the booking status should be:
      | processing |

  Scenario: Best available seat selection - single seat
    When buyer creates booking with best available seat selection:
      | seat_selection_mode | quantity |
      | best_available      |        1 |
    Then the response status code should be:
      | 201 |
    And the booking status should be:
      | processing |

  Scenario: Cannot select more than 4 tickets
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | seat_positions        |
      | manual              | 1-1,1-2,1-3,1-4,2-1 |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Maximum 4 tickets per booking |

  Scenario: Manual seat selection - single seat
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | seat_positions |
      | manual              | 2-3            |
    Then the response status code should be:
      | 201 |
    And the booking status should be:
      | processing |
