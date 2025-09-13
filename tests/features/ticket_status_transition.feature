Feature: Ticket Status Transition
  As a ticketing system
  I want to enforce proper ticket status transitions
  So that tickets follow valid business workflows with payment timeouts

  Background:
    Given the following users exist:
      | user_id | email            | role   |
      |       1 | seller1@test.com | seller |
      |       2 | buyer1@test.com  | buyer  |
      |       3 | buyer2@test.com  | buyer  |
    And the following events exist:
      | event_id | name      | venue          | date       | seller_id | seating_config                                                                                       |
      |        1 | Concert A | Madison Square | 2025-10-01 |         1 | {"sections": [{"section": "A", "subsections": [{"subsection": 1, "rows": 5, "seats_per_row": 10}]}]} |
      |        2 | Concert B | Staples Center | 2025-11-01 |         1 | {"sections": [{"section": "B", "subsections": [{"subsection": 1, "rows": 3, "seats_per_row": 5}]}]}  |
    And tickets exist for events:
      | event_id | ticket_count | price | status    |
      |        1 |           10 |  1000 | available |
      |        2 |            5 |  1500 | available |

  Scenario: Normal flow - Available ticket to reserved to sold
    Given I am logged in as:
      | email           | password |
      | buyer1@test.com | P@ssw0rd |
    When buyer reserves tickets:
      | buyer_id | event_id | ticket_count |
      |        2 |        1 |            2 |
    Then the response status code should be:
      | 200 |
    And tickets should transition to reserved status:
      | event_id | status   | count | buyer_id |
      |        1 | reserved |     2 |        2 |
    When buyer creates order for reserved tickets:
      | buyer_id | event_id | ticket_ids |
      |        2 |        1 |        1,2 |
    Then order should be created with status:
      | status          |
      | pending_payment |
    When buyer pays for the order within time limit
    Then the response status code should be:
      | 200 |
    And order status should transition to:
      | status |
      | paid   |
    And reserved tickets should transition to sold:
      | event_id | status | count | buyer_id |
      |        1 | sold   |     2 |        2 |
