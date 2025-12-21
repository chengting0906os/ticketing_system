@integration
Feature: Seat Release
  As a ticketing system
  I want to release reserved seats back to available
  So that cancelled bookings free up inventory

  Background:
    Given an event with seating configuration is initialized

  # Single Seat Release
  @smoke
  Rule: Release executor transitions seats from RESERVED to AVAILABLE

    Scenario: Release a single reserved seat
      Given subsection "A-2" has 3 rows with 20 seats
      And seat "2-11" is already reserved
      When I release seat "2-11" in subsection "A-2"
      Then the release should succeed
      And seat "2-11" should have status AVAILABLE

    Scenario: Release seat in first subsection
      Given subsection "A-1" has 2 rows with 20 seats
      And seat "1-5" is already reserved
      When I release seat "1-5" in subsection "A-1"
      Then the release should succeed
      And seat "1-5" should have status AVAILABLE

    Scenario: Verify bitfield status after release
      Given subsection "A-2" has 3 rows with 20 seats
      And seat "2-11" is already reserved
      And seat "2-11" bitfield status should be 1
      When I release seat "2-11" in subsection "A-2"
      Then seat "2-11" bitfield status should be 0

    # Batch Release
  Rule: Multiple seats can be released at once

    Scenario: Release multiple seats atomically
      Given subsection "A-1" has 2 rows with 5 seats
      And seats "1-1, 1-2, 2-1" are already reserved
      When I release seats "1-1, 1-2, 2-1" in subsection "A-1"
      Then the release should succeed
      And 3 seats should be released
      And seat "1-1" should have status AVAILABLE
      And seat "1-2" should have status AVAILABLE
      And seat "2-1" should have status AVAILABLE

    Scenario: Release seats from different rows
      Given subsection "A-1" has 3 rows with 4 seats
      And seats "1-1, 2-2, 3-3" are already reserved
      When I release seats "1-1, 2-2, 3-3" in subsection "A-1"
      Then the release should succeed
      And seat "1-1" should have status AVAILABLE
      And seat "2-2" should have status AVAILABLE
      And seat "3-3" should have status AVAILABLE

    # Idempotency
  Rule: Release is idempotent - releasing available seats is a no-op

    Scenario: Releasing an already available seat succeeds (idempotent)
      Given subsection "A-1" has 1 rows with 3 seats
      When I release seat "1-1" in subsection "A-1"
      Then the release should succeed
      And seat "1-1" should have status AVAILABLE

    Scenario: Double release of same seat succeeds (idempotent)
      Given subsection "A-1" has 1 rows with 3 seats
      And seat "1-2" is already reserved
      When I release seat "1-2" in subsection "A-1"
      Then the release should succeed
      And seat "1-2" should have status AVAILABLE
      When I release seat "1-2" in subsection "A-1"
      Then the release should succeed
      And seat "1-2" should have status AVAILABLE

    # Status Verification
  Rule: Released seats correctly update bitfield status

    Scenario: Verify multiple released seats have correct bitfield status
      Given subsection "A-1" has 2 rows with 3 seats
      And seats "1-1, 1-2, 2-1" are already reserved
      And seat "1-1" bitfield status should be 1
      And seat "1-2" bitfield status should be 1
      And seat "2-1" bitfield status should be 1
      When I release seats "1-1, 1-2, 2-1" in subsection "A-1"
      Then seat "1-1" bitfield status should be 0
      And seat "1-2" bitfield status should be 0
      And seat "2-1" bitfield status should be 0
