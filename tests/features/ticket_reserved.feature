Feature: Ticket Reservation by Buyer
  As a buyer
  I want to reserve tickets before purchasing
  So that I can secure my seats while completing payment

  Background:
    Given the following users exist:
      | user_id | email            | role   |
      |       1 | seller1@test.com | seller |
      |       2 | seller2@test.com | seller |
      |       3 | buyer1@test.com  | buyer  |
      |       4 | buyer2@test.com  | buyer  |
    And the following events exist:
      | event_id | name           | venue            | date       | seller_id | seating_config                                                                                                                                  |
      |        1 | Concert A      | Madison Square   | 2025-10-01 |         1 | {"sections": [{"section": "A", "subsections": [{"subsection": 1, "rows": 5, "seats_per_row": 10}]}]}                                          |
      |        2 | Concert B      | Staples Center   | 2025-11-01 |         1 | {"sections": [{"section": "B", "subsections": [{"subsection": 1, "rows": 3, "seats_per_row": 5}]}]}                                           |
      |        3 | Festival C     | Hollywood Bowl   | 2025-12-01 |         2 | {"sections": [{"section": "VIP", "subsections": [{"subsection": 1, "rows": 2, "seats_per_row": 8}]}]}                                         |

  Scenario: Buyer reserves available tickets
    Given tickets exist for event:
      | event_id | status    | price |
      |        1 | available |  1000 |
    When buyer reserves tickets:
      | buyer_id | event_id | ticket_count |
      |        3 |        1 |            2 |
    Then the response status code should be:
      | 200 |
    And reservation is created with:
      | reservation_id | buyer_id | ticket_count | status   | expires_in_minutes |
      |              1 |        3 |            2 | reserved |                 15 |
    And reserved tickets status should be:
      | status   | count |
      | reserved |     2 |

  Scenario: Buyer cannot reserve more tickets than available
    Given tickets exist with limited availability:
      | event_id | available_count | sold_count |
      |        1 |               2 |         48 |
    When buyer attempts to reserve tickets:
      | buyer_id | event_id | ticket_count |
      |        3 |        1 |            3 |
    Then the response status code should be:
      | 400 |
    And error message should contain:
      | Not enough available tickets |

  Scenario: Buyer cannot reserve already reserved tickets
    Given tickets are already reserved:
      | event_id | reserved_by | ticket_count |
      |        1 |           4 |            5 |
    When buyer attempts to reserve same tickets:
      | buyer_id | event_id | ticket_count |
      |        3 |        1 |            3 |
    Then the response status code should be:
      | 409 |
    And error message should contain:
      | Some tickets are already reserved |

  Scenario: Buyer can cancel their own reservation
    Given buyer has active reservation:
      | buyer_id | event_id | ticket_count | reservation_id |
      |        3 |        1 |            3 |              1 |
    When buyer cancels reservation:
      | buyer_id | reservation_id |
      |        3 |              1 |
    Then the response status code should be:
      | 200 |
    And reservation status should be:
      | status    |
      | cancelled |
    And tickets should return to available:
      | status    | count |
      | available |     3 |

  Scenario: Buyer cannot reserve more than 4 tickets per person
    Given tickets exist for event:
      | event_id | status    | price |
      |        1 | available |  1000 |
    When buyer attempts to reserve too many tickets:
      | buyer_id | event_id | ticket_count |
      |        3 |        1 |            5 |
    Then the response status code should be:
      | 400 |
    And error message should contain:
      | Maximum 4 tickets per person |