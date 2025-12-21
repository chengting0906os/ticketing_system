@integration
Feature: Seat Reservation
  As a ticketing system
  I want to reserve seats atomically
  So that concurrent reservation requests are handled correctly

  Background:
    Given an event with seating configuration is initialized

  # Manual Mode - Specific Seat Selection
  @smoke
  Rule: Manual mode reserves specific seats atomically

    Scenario: Reserve a single seat in manual mode
      Given subsection "A-1" has 1 rows with 3 seats
      When I request to reserve seat "1-1" in manual mode
      Then the reservation should succeed
      And seat "1-1" should have status RESERVED

    Scenario: Reserve multiple seats atomically in manual mode
      Given subsection "A-1" has 2 rows with 3 seats
      When I request to reserve seats "1-1, 1-2, 2-1" in manual mode
      Then the reservation should succeed
      And 3 seats should be reserved
      And all requested seats should have status RESERVED

    Scenario: Cannot reserve an already reserved seat
      Given subsection "A-1" has 1 rows with 2 seats
      And seat "1-1" is already reserved
      When I request to reserve seat "1-1" in manual mode
      Then the reservation should fail

    Scenario: Partial reservation fails atomically (all-or-nothing)
      Given subsection "A-1" has 1 rows with 3 seats
      And seat "1-2" is already reserved
      When I request to reserve seats "1-1, 1-2, 1-3" in manual mode
      Then the reservation should fail
      And seat "1-1" should have status AVAILABLE
      And seat "1-3" should have status AVAILABLE

  # Best Available Mode - Automatic Seat Selection
  Rule: Best available mode finds optimal consecutive seats

    Scenario: Find and reserve consecutive seats in a single row
      Given subsection "A-1" has 1 rows with 5 seats
      When I request 3 seats in best_available mode
      Then the reservation should succeed
      And I should receive consecutive seats "1-1, 1-2, 1-3"

    Scenario: Find consecutive seats in next row when current row is partial
      Given subsection "A-1" has 2 rows with 3 seats
      And seats "1-1, 1-2" are already reserved
      When I request 2 seats in best_available mode
      Then the reservation should succeed
      And I should receive consecutive seats "2-1, 2-2"

    Scenario: Fall back to scattered seats when no consecutive block exists
      Given subsection "A-1" has 1 rows with 3 seats
      And seat "1-2" is already reserved
      When I request 2 seats in best_available mode
      Then the reservation should succeed
      And I should receive scattered seats "1-1, 1-3"

    Scenario: Choose earliest available consecutive block
      Given subsection "A-1" has 3 rows with 4 seats
      And seats "1-1, 1-2" are already reserved
      When I request 2 seats in best_available mode
      Then the reservation should succeed
      And I should receive consecutive seats "1-3, 1-4"

  # Status Verification
  Rule: Reserved seats have correct RESERVED status (not SOLD)

    Scenario: Verify reserved seats have RESERVED status in bitfield
      Given subsection "A-1" has 2 rows with 5 seats
      When I request to reserve seats "1-1, 1-2, 2-1" in manual mode
      Then the reservation should succeed
      And seat "1-1" bitfield status should be 1
      And seat "1-2" bitfield status should be 1
      And seat "2-1" bitfield status should be 1
