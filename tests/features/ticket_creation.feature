Feature: Ticket Creation by Seller
  As a seller
  I want to create tickets for my events
  So that buyers can purchase tickets

  Scenario: Seller creates tickets for entire venue with batch operation
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    When seller creates tickets with:
      | seller_id | event_id | price |
      |         1 |        1 |  1000 |
    Then tickets are created successfully with:
      | count |
      |  2500 |



  Scenario: Cannot create tickets for other seller's event
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And another seller and event exist with:
      | seller_id | event_id |
      |         2 |        2 |
    When seller creates tickets with:
      | seller_id | event_id | price |
      |         1 |        2 |  2000 |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Not authorized to create tickets for this event |

  Scenario: Cannot create tickets twice for same event
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        4 |         1 |
    And all tickets exist with:
      | event_id | price |
      |        4 |  1000 |
    When seller creates tickets with:
      | seller_id | event_id | price |
      |         1 |        4 |  1500 |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Tickets already exist for this event |

  Scenario: Buyer cannot create tickets
    Given a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        5 |         1 |
    When buyer creates tickets with:
      | buyer_id | event_id | price |
      |        3 |        5 |  1000 |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |