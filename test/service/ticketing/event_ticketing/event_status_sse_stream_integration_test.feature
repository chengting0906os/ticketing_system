@api
Feature: Seat Status SSE Stream
  As a user
  I want to receive real-time seat status updates via SSE
  So that I can see seat availability changes instantly

  Background:
    Given a seller exists
    And an event exists with:
      | name      | description | is_active | status    | venue_name  | seating_config                                                                                                                                                                        |
      | SSE Event | SSE Test    | true      | available | Large Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 3000, "subsections": 2}, {"name": "B", "price": 2000, "subsections": 1}, {"name": "C", "price": 1500, "subsections": 1}]} |

  Scenario: User receives initial seat status via SSE
    When user connects to SSE stream for event {event_id}
    Then SSE connection should be established
    And initial status event should be received with:
      | event_type     | sections_count |
      | initial_status | 4              |
    And section stats should include:
      | section | subsection | total | available |
      | A       | 1          | 50    | 50        |

  Scenario: User receives status updates when seats are reserved
    Given user is connected to SSE stream for event {event_id}
    When section stats are updated with:
      | section | subsection | available | reserved | sold |
      | A       | 1          | 45        | 5        | 0    |
    Then status update event should be received with:
      | event_type    |
      | status_update |
    And updated section stats should show:
      | section | subsection | total | available | reserved |
      | A       | 1          | 50    | 45        | 5        |

  Scenario: User receives error when connecting to non-existent event
    When user connects to SSE stream for event 999
    Then the response status code should be 404
    And the error message should contain "Event not found"

  Scenario: Multiple users receive same status updates
    When 3 users connect to SSE stream for event {event_id}
    Then all 3 users should receive status update event
    And all users should see same section stats:
      | section | subsection | available | reserved |
      | A       | 1          | 50        | 0        |
