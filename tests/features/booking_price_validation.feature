Feature: Order Price Validation
  As a marketplace system
  I want to validate ticket prices and booking totals properly
  So that bookings maintain data integrity and business rules

  Background:
    Given a seller exists:
      | email           | password | name        | role   |
      | seller@test.com | P@ssw0rd | Test Seller | seller |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |

  Scenario: Order total price calculated from selected tickets
    Given tickets exist for event:
      | event_id | status    | price |
      |        1 | available |  1000 |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When buyer creates booking with tickets:
      | ticket_ids |
      |        1,2 |
    Then the response status code should be:
      | 201 |
    And the booking should be created with:
      | total_price | status          | created_at | paid_at |
      |        2000 | pending_payment | not_null   | null    |

  Scenario: Order with single ticket calculates correct price
    Given tickets exist for event:
      | event_id | status    | price |
      |        1 | available |  1500 |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When buyer creates booking with tickets:
      | ticket_ids |
      |          1 |
    Then the response status code should be:
      | 201 |
    And the booking should be created with:
      | total_price | status          | created_at | paid_at |
      |        1500 | pending_payment | not_null   | null    |

  Scenario: Order with different priced tickets calculates correct total
    Given tickets exist for event:
      | event_id | status    | price |
      |        1 | available |  1000 |
      |        1 | available |  1500 |
      |        1 | available |  2000 |
    And a buyer exists:
      | email          | password | name       | role  |
      | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
    And I am logged in as:
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    When buyer creates booking with tickets:
      | ticket_ids |
      |      1,2,3 |
    Then the response status code should be:
      | 201 |
    And the booking should be created with:
      | total_price | status          | created_at | paid_at |
      |        4500 | pending_payment | not_null   | null    |
