Feature: Order Creation
  As a buyer
  I want to create orders for available events
  So that I can purchase items

  Scenario: Successfully create order for available event
    Given a seller with a event:
      | name       | description    | price | is_active | status    | venue_name   | seating_config                                                                                 |
      | Test Event | For order test |  1000 | true      | available | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer creates an order for the event
    Then the response status code should be:
      | 201 |
    And the order should be created with:
      | price | status          | created_at | paid_at |
      |  1000 | pending_payment | not_null   | null    |
    And the event status should be:
      | reserved |

  Scenario: Cannot create order for reserved event
    Given a seller with a event:
      | name       | description      | price | is_active | status   | venue_name  | seating_config                                                                                 |
      | Test Event | Already reserved |  1000 | true      | reserved | Taipei Dome | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to create an order for the event
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Event not available |

  Scenario: Cannot create order for inactive event
    Given a seller with a event:
      | name       | description    | price | is_active | status    | venue_name   | seating_config                                                                                 |
      | Test Event | Inactive event |  1000 | false     | available | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer tries to create an order for the event
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Event not active |

  Scenario: Seller cannot create order
    Given a seller with a event:
      | name       | description    | price | is_active | status    | venue_name  | seating_config                                                                                 |
      | Test Event | For order test |  1000 | true      | available | Taipei Dome | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    And a seller user exists
      | email           | password | name   | role   |
      | seller@test.com | P@ssw0rd | Seller | seller |
    And I am logged in as:
      | email           | password |
      | seller@test.com | P@ssw0rd |
    When the seller tries to create an order for their own event
    Then the response status code should be:
      | 403 |
    And the error message should contain:
      | Only buyers can perform this action |
