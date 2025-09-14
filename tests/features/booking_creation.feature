Feature: Event and Ticket Creation by Seller
  As a seller
  I want to create events with seating configuration
  So that tickets are automatically created for buyers to purchase

  Scenario: Seller creates event with seating config and tickets are auto-created
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When seller creates event with seating config:
      | name       | description    | venue_name   | seating_config                                                                                                        |
      | Test Event | Great concert  | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 5, "seats_per_row": 10}]}]} |
    Then the response status code should be:
      | 201 |
    And the event should be created with:
      | name       | status    | is_active |
      | Test Event | available | true      |
    And tickets should be auto-created with:
      | count | price | status    |
      | 50    | 1000  | available |

  Scenario: Cannot create event without valid seating config
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When seller creates event with invalid seating config:
      | name       | description | venue_name   | seating_config |
      | Test Event | Bad config  | Taipei Arena | invalid_json   |
    Then the response status code should be:
      | 422 |
    And the error message should contain:
      | Input should be a valid dictionary |

  Scenario: Seller creates event with multiple sections and subsections
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When seller creates event with complex seating config:
      | name           | description      | venue_name  | seating_config                                                                                                                                                                                                                |
      | Big Concert    | Multi-section    | Taipei Dome | {"sections": [{"name": "A", "price": 1500, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 20}]}, {"name": "B", "price": 1200, "subsections": [{"number": 1, "rows": 15, "seats_per_row": 25}]}]} |
    Then the response status code should be:
      | 201 |
    And tickets should be auto-created with:
      | count | status    |
      | 575   | available |

  Scenario: Buyer cannot create events
    Given a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When buyer tries to create event with seating config:
      | name       | description | venue_name   | seating_config                                                                                                        |
      | Test Event | Unauthorized | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 5, "seats_per_row": 10}]}]} |
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only sellers can perform this action |

  Scenario: Cannot create event with negative ticket price
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When seller creates event with negative ticket price:
      | name       | description | venue_name   | seating_config                                                                                                       |
      | Test Event | Bad price   | Taipei Arena | {"sections": [{"name": "A", "price": -500, "subsections": [{"number": 1, "rows": 5, "seats_per_row": 10}]}]} |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Ticket price must be positive |

  Scenario: Cannot create event with zero ticket price
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When seller creates event with zero ticket price:
      | name       | description | venue_name   | seating_config                                                                                                    |
      | Free Event | Zero price  | Taipei Arena | {"sections": [{"name": "A", "price": 0, "subsections": [{"number": 1, "rows": 5, "seats_per_row": 10}]}]} |
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Ticket price must be positive |
