@integration
Feature: Booking with Insufficient Seats
  As a system
  I want to check seat availability before creating bookings
  So that users get immediate feedback about insufficient seats

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
      | name         | venue_name | seating_config                                                                                            |
      | Small Event  | Small Hall | {"sections": [{"name": "B", "price": 500, "subsections": [{"number": 1, "rows": 1, "seats_per_row": 2}]}]} |

  Scenario: Fail fast when requesting more seats than available
    When buyer creates booking with best available in section:
      | seat_selection_mode | section | subsection | quantity |
      | best_available      | B       |          1 |        4 |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Insufficient seats available in section B-1 |
