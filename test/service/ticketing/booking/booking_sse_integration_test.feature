@integration
Feature: Booking Status SSE Endpoint
  As a buyer
  I want to receive real-time booking status updates
  So that I can track my booking progress without polling

  Background:
    Given I am logged in as a seller
    And an event exists with:
      | name         | description | is_active | status    | seller_id | venue_name   | seating_config                                                                        |
      | Test Concert | Test event  | true      | available | 1         | Taipei Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And I am logged in as a buyer

  @smoke
  Scenario: Buyer can connect to SSE endpoint
    When I subscribe to SSE endpoint "/api/booking/event/{event_id}/sse"
    Then SSE connection should be established

  Scenario: Unauthenticated user cannot connect to SSE
    Given I am not authenticated
    When I call GET "/api/booking/event/{event_id}/sse"
    Then the response status code should be 401

  Scenario: Seller can also connect to SSE endpoint
    Given I am logged in as a seller
    When I subscribe to SSE endpoint "/api/booking/event/{event_id}/sse"
    Then SSE connection should be established

  @smoke
  Scenario: SSE broadcaster can publish and receive success events
    Given I am subscribed to SSE for event {event_id}
    When SSE event is published with:
      | event_type      | event_id   | booking_id                           | status          | tickets                                                                                                            |
      | booking_updated | {event_id} | 01900000-0000-7000-8000-000000000001 | PENDING_PAYMENT | [{"id": 1, "section": "A", "subsection": 1, "row": 1, "seat": 1, "price": 1000, "status": "reserved"}] |
    Then I should receive SSE event with:
      | event_type      | status          | booking_id                           |
      | booking_updated | PENDING_PAYMENT | 01900000-0000-7000-8000-000000000001 |

  Scenario: SSE broadcaster delivers failure events with error message
    Given I am subscribed to SSE for event {event_id}
    When SSE event is published with:
      | event_type      | event_id   | booking_id                           | status | tickets | error_message           |
      | booking_updated | {event_id} | 01900000-0000-7000-8000-000000000002 | FAILED | []      | No seats available |
    Then I should receive SSE event with:
      | event_type      | status | error_message           |
      | booking_updated | FAILED | No seats available |
