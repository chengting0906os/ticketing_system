Feature: Event Ticket Management
  As a user (seller or buyer)
  I want to manage and view tickets for events
  So that I can handle event inventory and purchases

  Scenario: Buyer can list available tickets for purchase
    Given a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    When buyer lists available tickets with:
      | buyer_id | event_id |
      |        2 |        1 |
    Then the response status code should be:
      | 200 |
    And available tickets should be returned with count:
      | 50 |
    And tickets should include detailed information:
      | seat_numbers | prices | sections |
      | true         | true   | true     |

  Scenario: Seller lists tickets by subsection
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    When seller lists tickets by section with:
      | seller_id | event_id | section | subsection |
      |         1 |        1 | A       |          1 |
    Then the response status code should be:
      | 200 |
    And section tickets should be returned with count:
      | 50 |

  Scenario: Buyer receives error when listing tickets for non-existent event
    Given a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    When buyer lists available tickets with:
      | buyer_id | event_id |
      |        3 |      999 |
    Then the response status code should be:
      | 404 |
    And the error message should contain:
      | Event not found |
