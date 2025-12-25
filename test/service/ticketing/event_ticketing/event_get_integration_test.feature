@integration
Feature: Event Detail
  As a user
  I want to view event details with subsection statistics
  So that I can see seat availability for each subsection

  Background:
    Given a seller exists
    And an event exists with:
      | name      | description | is_active | status    | venue_name  | seating_config                                                                                                                                                                        |
      | SSE Event | SSE Test    | true      | available | Large Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 3000, "subsections": 2}, {"name": "B", "price": 2000, "subsections": 1}, {"name": "C", "price": 1500, "subsections": 1}]} |

  @smoke
  Scenario: Get event details with subsection status
    When I call GET "/api/event/{event_id}"
    Then the response status code should be 200
    And the response data should include:
      | id       | name      | description | seller_id | is_active | status    | venue_name  | seating_config | sections | stats    |
      | not_null | SSE Event | SSE Test    | not_null  | true      | available | Large Arena | not_null       | not_null | not_null |
    And all subsection stats should be returned:
      | section | subsection | price | available | reserved | sold |
      | A       | 1          | 3000  | 50        | 0        | 0    |
      | A       | 2          | 3000  | 50        | 0        | 0    |
      | B       | 1          | 2000  | 50        | 0        | 0    |
      | C       | 1          | 1500  | 50        | 0        | 0    |

  Scenario: Get event details for non-existent event
    When I call GET "/api/event/999"
    Then the response status code should be 404
    And the error message should contain "Event not found"
