Feature: Order Price Validation
  As a marketplace system
  I want to validate order prices properly
  So that orders maintain data integrity and business rules

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |

  Scenario: Cannot create order with negative price event
    Given a event exists with negative price:
      | name       | description      | price | seller_id | is_active | status    |
      | Test Event | Test Description |  -100 |         1 | true      | available |
    When the buyer tries to create an order for the negative price event
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |

  Scenario: Cannot create order with zero price event
    Given a event exists with zero price:
      | name       | description      | price | seller_id | is_active | status    |
      | Free Event | Test Description |     0 |         1 | true      | available |
    When the buyer tries to create an order for the zero price event
    Then the response status code should be:
      | 400 |
    And the error message should contain:
      | Price must be positive |

  Scenario: Order price matches event price at creation time
    Given a event exists:
      | name       | description      | price | seller_id | is_active | status    | venue_name   | seating_config                                                                                 |
      | Test Event | Test Description |  1000 |         1 | true      | available | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When the buyer creates an order for the event
    Then the order should be created with:
      | price | status          |
      |  1000 | pending_payment |
    And the order price should be 1000

  Scenario: Event price changes do not affect existing orders
    Given a event exists:
      | name       | description      | price | seller_id | is_active | status    | venue_name  | seating_config                                                                                 |
      | Test Event | Test Description |  1000 |         1 | true      | available | Taipei Dome | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the event
    When the event price is updated to 2000
    Then the existing order price should remain 1000
    And the event status should be "reserved"

  Scenario: New orders use updated event price
    Given a event exists:
      | name       | description      | price | seller_id | is_active | status    | venue_name   | seating_config                                                                                 |
      | Test Event | Test Description |  1000 |         1 | true      | available | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the event
    And the event price is updated to 2000
    And the buyer cancels the order to release the event
    When another buyer creates an order for the same event
    Then the new order should have price 2000

  Scenario: Paid order price remains unchanged after event price update
    Given a event exists:
      | name       | description      | price | seller_id | is_active | status    | venue_name  | seating_config                                                                                 |
      | Test Event | Test Description |  1500 |         1 | true      | available | Taipei Dome | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    And the buyer creates an order for the event
    And the buyer pays for the order
    When the event price is updated to 3000
    Then the paid order price should remain 1500
    And the order status should remain "paid"
