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

  Scenario: Manual seat selection - happy path
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | selected_seats  |
      | manual              | A-1-1-1,A-1-1-2 |
    Then the response status code should be:
      | 201 |
    And the booking should contain tickets with seats:
      | seat_number |
      | A-1-1-1     |
      | A-1-1-2     |
    And the selected tickets should have status:
      | reserved |

  Scenario: Manual seat selection - single seat
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | selected_seats |
      | manual              | A-1-2-3        |
    Then the response status code should be:
      | 201 |
    And the booking should contain tickets with seats:
      | seat_number |
      | A-1-2-3     |

  Scenario: Best available seat selection - happy path
    When buyer creates booking with best available seat selection:
      | seat_selection_mode | quantity |
      | best_available      |        3 |
    Then the response status code should be:
      | 201 |
    And the booking should contain consecutive available seats:
      | count |
      | 3     |
    And the selected seats should be from the lowest available row

  Scenario: Best available seat selection - single seat
    When buyer creates booking with best available seat selection:
      | seat_selection_mode | quantity |
      | best_available      |        1 |
    Then the response status code should be:
      | 201 |
    And the booking should contain available seat:
      | count |
      | 1     |

  Scenario: Legacy booking approach still works
    When buyer creates booking with legacy ticket selection:
      | ticket_ids |
      |        1,2 |
    Then the response status code should be:
      | 201 |
    And the booking should contain tickets:
      | count |
      | 2     |

  Scenario: Cannot select more than 4 tickets
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | selected_seats                          |
      | manual              | A-1-1-1,A-1-1-2,A-1-1-3,A-1-1-4,A-1-2-1 |
    Then the response status code should be:
      | 422 |
    And the error message should contain:
      | Maximum 4 tickets per booking |

  Scenario: Cannot select unavailable seats
    Given seats are already booked:
      | seat_number |
      | A-1-1-1     |
      | A-1-1-2     |
    When buyer creates booking with manual seat selection:
      | seat_selection_mode | selected_seats  |
      | manual              | A-1-1-1,A-1-1-3 |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Seat A-1-1-1 is not available |
