Feature: Ticket Listing by Seller
  As a seller
  I want to list tickets for my events
  So that I can manage my inventory

  Scenario: Seller lists all tickets for their event
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        1 |         1 |
    And all tickets exist with:
      | event_id | price |
      |        1 |  1000 |
    When seller lists all tickets with:
      | seller_id | event_id |
      |         1 |        1 |
    Then the response status code should be:
      | 200 |
    And tickets should be returned with count:
      | 2500 |

  Scenario: Seller lists tickets by section
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        2 |         1 |
    And all tickets exist with:
      | event_id | price |
      |        2 |  1000 |
    When seller lists tickets by section with:
      | seller_id | event_id | section |
      |         1 |        2 | A       |
    Then the response status code should be:
      | 200 |
    And section tickets should be returned with count:
      | 500 |

  Scenario: Cannot list tickets for other seller's event
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And another seller and event exist with:
      | seller_id | event_id |
      |         2 |        3 |
    And all tickets exist with:
      | event_id | price |
      |        3 |  1000 |
    When seller lists all tickets with:
      | seller_id | event_id |
      |         1 |        3 |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Not authorized to view tickets for this event |

  Scenario: Buyer can list available tickets for purchase
    Given a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        4 |         2 |
    And all tickets exist with:
      | event_id | price |
      |        4 |  1000 |
    When buyer lists available tickets with:
      | buyer_id | event_id |
      |        3 |        4 |
    Then the response status code should be:
      | 200 |
    And available tickets should be returned with count:
      | 2500 |

  Scenario: List tickets for event with no tickets
    Given a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        5 |         1 |
    When seller lists all tickets with:
      | seller_id | event_id |
      |         1 |        5 |
    Then the response status code should be:
      | 200 |
    And tickets should be returned with count:
      | 0 |

  Scenario: Buyer cannot access section-specific ticket listing
    Given a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        6 |         2 |
    And all tickets exist with:
      | event_id | price |
      |        6 |  1000 |
    When buyer attempts to access section tickets with:
      | buyer_id | event_id | section |
      |        3 |        6 | A       |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |

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

  Scenario: Buyer should see ticket details including seat numbers and prices
    Given a buyer exists:
      | email           | password | name        | role  |
      | buyer1@test.com | P@ssw0rd | Test Buyer1 | buyer |
    And a seller exists:
      | email            | password | name         | role   |
      | seller1@test.com | P@ssw0rd | Test Seller1 | seller |
    And an event exists with:
      | event_id | seller_id |
      |        7 |         2 |
    And all tickets exist with:
      | event_id | price |
      |        7 |  1500 |
    When buyer lists available tickets with detailed view:
      | buyer_id | event_id |
      |        3 |        7 |
    Then the response status code should be:
      | 200 |
    And tickets should include detailed information:
      | seat_numbers | prices | sections |
      |         true |   true |     true |