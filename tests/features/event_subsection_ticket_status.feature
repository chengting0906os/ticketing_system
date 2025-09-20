Feature: Event Status with Price Groups
  As a user (seller or buyer)
  I want to check event status grouped by price
  So that I can see subsection availability organized by price tiers

  Scenario: Get event status with all subsections available
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with price groups:
      | event_id | seller_id |
      |        1 |         1 |
    And all tickets exist for price groups with:
      | event_id |
      |        1 |
    When user requests event status:
      | event_id |
      |        1 |
    Then the response status code should be:
      | 200 |
    And the event status should contain price groups:
      | price | subsections_count |
      |  8800 |                 4 |
      |  8000 |                 2 |
      |  7500 |                 4 |
    And subsections should all be available:
      | price | subsection | total_seats | available_seats | status    |
      |  8800 |          1 |         100 |             100 | Available |
      |  8800 |          2 |         100 |             100 | Available |
      |  8800 |          3 |         100 |             100 | Available |
      |  8800 |          4 |         100 |             100 | Available |
      |  8000 |          5 |         100 |             100 | Available |
      |  8000 |          6 |         100 |             100 | Available |
      |  7500 |          7 |         100 |             100 | Available |
      |  7500 |          8 |         100 |             100 | Available |
      |  7500 |          9 |         100 |             100 | Available |
      |  7500 |         10 |         100 |             100 | Available |

  Scenario: Get event status with some subsections partially booked
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And an event exists with price groups:
      | event_id | seller_id |
      |        2 |         1 |
    And all tickets exist for price groups with:
      | event_id |
      |        2 |
    And some tickets are reserved:
      | event_id | buyer_id | subsection | ticket_count |
      |        2 |        2 |          8 |            4 |
    And some tickets are sold:
      | event_id | subsection | ticket_count |
      |        2 |          5 |            3 |
    When user requests event status:
      | event_id |
      |        2 |
    Then the response status code should be:
      | 200 |
    And subsections should have mixed status:
      | price | subsection | total_seats | available_seats | status                |
      |  8000 |          5 |         100 |              97 | 97 seat(s) remaining  |
      |  7500 |          8 |         100 |              96 | 96 seat(s) remaining  |

  Scenario: Get event status with multiple subsections having different statuses
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And an event exists with price groups:
      | event_id | seller_id |
      |        3 |         1 |
    And all tickets exist for price groups with:
      | event_id |
      |        3 |
    And some tickets are reserved:
      | event_id | buyer_id | subsection | ticket_count |
      |        3 |        2 |          1 |            2 |
    And some tickets are sold:
      | event_id | subsection | ticket_count |
      |        3 |          2 |            1 |
      |        3 |          7 |            4 |
    When user requests event status:
      | event_id |
      |        3 |
    Then the response status code should be:
      | 200 |
    And price groups should have varied statuses:
      | price | has_available | has_partial |
      |  8800 |          true |        true |
      |  8000 |          true |       false |
      |  7500 |          true |        true |
    And specific subsections should show:
      | price | subsection | available_seats | status                |
      |  8800 |          1 |              98 | 98 seat(s) remaining  |
      |  8800 |          2 |              99 | 99 seat(s) remaining  |
      |  8800 |          3 |             100 | Available             |
      |  8800 |          4 |             100 | Available             |
      |  7500 |          7 |              96 | 96 seat(s) remaining  |