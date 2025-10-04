@integration
Feature: Seat Status SSE Stream
  As a user
  I want to receive real-time seat status updates via SSE
  So that I can see seat availability changes instantly

  Scenario: User receives initial seat status via SSE
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    When user connects to SSE stream for event:
      | event_id |
      |        1 |
    Then SSE connection should be established
    And initial status event should be received with:
      | event_type     | sections_count |
      | initial_status |            100 |
    And section stats should include:
      | section_id | total | available |
      | A-1        |   500 |       500 |

  Scenario: User receives status updates when seats are reserved
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    And user is connected to SSE stream for event 1
    When section stats are updated with:
      | section_id | available | reserved | sold |
      | A-1        |       495 |        5 |    0 |
    Then status update event should be received with:
      | event_type    |
      | status_update |
    And updated section stats should show:
      | section_id | total | available | reserved |
      | A-1        |   500 |       495 |        5 |

  Scenario: User receives error when connecting to non-existent event
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    When user connects to SSE stream for event:
      | event_id |
      |      999 |
    Then the response status code should be:
      | 404 |
    And the error message should contain:
      | Event not found |

  Scenario: Multiple users receive same status updates
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    When 3 users connect to SSE stream for event 1
    Then all 3 users should receive status update event
    And all users should see same section stats:
      | section_id | available | reserved |
      | A-1        |       500 |        0 |
