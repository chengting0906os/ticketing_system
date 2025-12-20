@integration
Feature: Booking Payment
  As a buyer
  I want to pay for my bookings
  So that I can complete the purchase

  Background:
    Given a seller exists
    And a buyer exists
    And an event exists with:
      | name         | description | is_active | status    | seller_id | venue_name   | seating_config                                                                         |
      | Test Concert | Test event  | true      | available | 1         | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And I am logged in as a buyer

  @smoke
  Scenario: Successfully pay for an booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 1000        | pending_payment |
    When I call POST "/api/booking/{booking.id}/pay" with
      | card_number      |
      | 4242424242424242 |
    And I call GET "/api/booking/{booking.id}"
    Then the response status code should be 200
    And the response data should include:
      | status    | created_at | paid_at  |
      | completed | not_null   | not_null |
    And the tickets should have status:
      | status |
      | sold   |

  Scenario: Cannot pay for already paid booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status    |
      | 2        | 1        | 1000        | completed |
    When I call POST "/api/booking/{booking.id}/pay" with
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be 400
    And the error message should contain "Booking already paid"

  Scenario: Cannot pay for cancelled booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status    |
      | 2        | 1        | 1000        | cancelled |
    When I call POST "/api/booking/{booking.id}/pay" with
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be 400
    And the error message should contain "Cannot pay for cancelled booking"

  Scenario: Cannot pay for processing booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status     |
      | 2        | 1        | 1000        | processing |
    When I call POST "/api/booking/{booking.id}/pay" with
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be 400
    And the error message should contain "Booking is not in a payable state"

  Scenario: Cannot pay for failed booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status |
      | 2        | 1        | 1000        | failed |
    When I call POST "/api/booking/{booking.id}/pay" with
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be 400
    And the error message should contain "Booking is not in a payable state"

  Scenario: Only buyer can pay for their booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 1000        | pending_payment |
    And I am logged in as a buyer with
      | email            | password |
      | another@test.com | P@ssw0rd |
    When I call POST "/api/booking/{booking.id}/pay" with
      | card_number      |
      | 4242424242424242 |
    Then the response status code should be 403
    And the error message should contain "Only the buyer can pay for this booking"

  Scenario: Cancel unpaid booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 1000        | pending_payment |
    When I call PATCH "/api/booking/{booking.id}"
    And I call GET "/api/booking/{booking.id}"
    Then the response status code should be 200
    And the response data should include:
      | status    | created_at | paid_at |
      | cancelled | not_null   | null    |

  Scenario: Cannot cancel completed booking
    Given a booking exists with:
      | buyer_id | event_id | total_price | status    |
      | 2        | 1        | 1000        | completed |
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 400
    And the error message should contain "Cannot cancel completed booking"
