@api
Feature: Booking Status SSE Stream
  As a buyer
  I want to receive real-time booking status updates via SSE
  So that I can see my booking status changes instantly

  Background:
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And an event exists with:
      | event_id                             | seller_id                            |
      | 019a1af7-0000-7003-0000-000000000020 | 019a1af7-0000-7002-0000-000000000020 |

  @smoke
  Scenario: Buyer receives initial booking status when connecting to SSE
    Given buyer1@test.com is logged in
    And a booking exists with status "PROCESSING":
      | booking_id                           | buyer_id                             | event_id                             |
      | 019a1af7-0000-7004-0000-000000000020 | 019a1af7-0000-7001-0000-000000000020 | 019a1af7-0000-7003-0000-000000000020 |
    When buyer connects to SSE stream for booking:
      | booking_id                           |
      | 019a1af7-0000-7004-0000-000000000020 |
    Then booking SSE connection should be established
    And booking initial status event should be received with:
      | event_type     | booking_id                           | status     |
      | initial_status | 019a1af7-0000-7004-0000-000000000020 | processing |

  Scenario: Buyer receives PENDING_PAYMENT status when seats are reserved
    Given buyer1@test.com is logged in
    And buyer creates a booking for event 019a1af7-0000-7003-0000-000000000020:
      | section | subsection | quantity | selection_mode | seat_positions |
      | A       | 1          | 2        | manual         | 1-1,1-2        |
    And buyer is connected to SSE stream for the created booking
    When the seat reservation is processed successfully
    Then status update event should be received with:
      | event_type     | status          |
      | seats_reserved | PENDING_PAYMENT |
    And the event should include seat details:
      | reserved_seats  | total_price |
      | A-1-1-1,A-1-1-2 | 2000        |

  Scenario: Buyer receives FAILED status when seat reservation fails
    Given buyer1@test.com is logged in
    And buyer creates a booking for event 019a1af7-0000-7003-0000-000000000020:
      | section | subsection | quantity | selection_mode | seat_positions |
      | A       | 1          | 2        | manual         | 1-1,1-2        |
    And buyer is connected to SSE stream for the created booking
    And seat 1-1 is already reserved by another buyer
    When the seat reservation is processed
    Then status update event should be received with:
      | event_type     | status |
      | booking_failed | FAILED |
    And the event should include error message:
      | error_message                 |
      | Seat A-1-1-1 is not available |

  Scenario: Buyer receives COMPLETED status after successful payment
    Given buyer1@test.com is logged in
    And a booking exists with status "pending_payment":
      | booking_id                           | buyer_id                             | event_id                             |
      | 019a1af7-0000-7004-0000-000000000021 | 019a1af7-0000-7001-0000-000000000020 | 019a1af7-0000-7003-0000-000000000020 |
    And the booking has reserved seats:
      | seat_positions  |
      | A-1-1-3,A-1-1-4 |
    And buyer is connected to SSE stream for booking 019a1af7-0000-7004-0000-000000000021
    When buyer1@test.com pays for the booking with card "4111111111111111"
    Then status update event should be received with:
      | event_type        | status    |
      | payment_completed | COMPLETED |
    And the event should include payment details:
      | payment_id | paid_at           |
      | PAY_MOCK_* | 2025-*-*T*:*:*.*Z |

  Scenario: Buyer receives CANCELLED status when cancelling booking
    Given buyer1@test.com is logged in
    And a booking exists with status "pending_payment":
      | booking_id                           | buyer_id                             | event_id                             |
      | 019a1af7-0000-7004-0000-000000000022 | 019a1af7-0000-7001-0000-000000000020 | 019a1af7-0000-7003-0000-000000000020 |
    And the booking has reserved seats:
      | seat_positions  |
      | A-1-1-5,A-1-1-6 |
    And buyer is connected to SSE stream for booking 019a1af7-0000-7004-0000-000000000022
    When buyer1@test.com cancels their booking
    Then status update event should be received with:
      | event_type        | status    |
      | booking_cancelled | CANCELLED |
    And the event should include cancellation timestamp

  Scenario: Buyer cannot connect to another buyer's booking SSE stream
    Given buyer1@test.com is logged in
    And another buyer exists:
      | email           | password | name        | role  |
      | buyer2@test.com | P@ssw0rd | Test Buyer2 | buyer |
    And a booking exists for buyer2@test.com:
      | booking_id                           | buyer_id                             | event_id                             |
      | 019a1af7-0000-7004-0000-000000000023 | 019a1af7-0000-7001-0000-000000000021 | 019a1af7-0000-7003-0000-000000000020 |
    When buyer1@test.com attempts to connect to SSE stream for booking:
      | booking_id                           |
      | 019a1af7-0000-7004-0000-000000000023 |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Forbidden |
