Feature: Event Deletion
  As a seller
  I want to delete my events when != reserved

  Scenario: Delete an available event
    Given a event exists with:
      | seller_id | name      | description    | price | is_active | status    | venue_name   | seating_config                                                                                 |
      |         1 | Test Item | Item to delete |  1000 | true      | available | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    When I delete the event
    Then the response status code should be:
      | 204 |
    And the event should not exist

  Scenario: Cannot delete a reserved event
    Given a event exists with:
      | seller_id | name      | description   | price | is_active | status   | venue_name  | seating_config                                                                                 |
      |         1 | Test Item | Reserved item |  1000 | true      | reserved | Taipei Dome | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    When I try to delete the event
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot delete reserved event |

  Scenario: Cannot delete a sold event
    Given a event exists with:
      | seller_id | name      | description | price | is_active | status | venue_name   | seating_config                                                                                 |
      |         1 | Test Item | Sold item   |  1000 | true      | sold   | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
    When I try to delete the event
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Cannot delete sold event |
