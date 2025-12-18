@integration
Feature: Event Ticket Management
  As a user (seller or buyer)
  I want to manage and view tickets for events
  So that I can handle event inventory and purchases

  Background:
    Given a seller exists

  @smoke
  Scenario: Buyer can list available tickets for purchase
    Given a buyer exists
    And an event exists with:
      | name      | description | is_active | status    | venue_name  | seating_config                                                                                                                                                                        |
      | SSE Event | SSE Test    | true      | available | Large Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 3000, "subsections": 2}, {"name": "B", "price": 2000, "subsections": 1}, {"name": "C", "price": 1500, "subsections": 1}]} |
    When I call GET "/api/reservation/{event_id}/sections/A/subsection/1/seats"
    Then the response status code should be 200
    And available tickets should be returned with count:
      | 50 |

  Scenario: Seller lists tickets by subsection
    Given an event exists with:
      | name      | description | is_active | status    | venue_name  | seating_config                                                                                                                                                                        |
      | SSE Event | SSE Test    | true      | available | Large Arena | {"rows": 5, "cols": 10, "sections": [{"name": "A", "price": 3000, "subsections": 2}, {"name": "B", "price": 2000, "subsections": 1}, {"name": "C", "price": 1500, "subsections": 1}]} |
    When I call GET "/api/reservation/{event_id}/sections/A/subsection/1/seats"
    Then the response status code should be 200
    And section tickets should be returned with count:
      | 50 |

  Scenario: Buyer receives error when listing tickets for non-existent event
    Given a buyer exists
    When I call GET "/api/reservation/999/sections/A/subsection/1/seats"
    Then the response status code should be 404
    And the error message should contain "Event not found"
