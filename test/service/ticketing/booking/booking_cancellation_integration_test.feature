@integration
Feature: Booking Cancellation
  As a buyer
  I want to cancel my unpaid bookings
  So that I can release events I no longer want to purchase

  Background:
    Given a seller exists
    And a buyer exists

  @smoke
  Scenario: Successfully cancel unpaid booking
    Given an event exists with:
      | name         | description     | is_active | status    | seller_id | venue_name   | seating_config                                                                         |
      | Rock Concert | For cancel test | true      | available | 1         | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 2000        | pending_payment |
    And I am logged in as a buyer
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 200
    And the response data should include:
      | status    |
      | cancelled |

  Scenario: Successfully cancel processing booking
    Given an event exists with:
      | name           | description      | is_active | status    | seller_id | venue_name   | seating_config                                                                         |
      | Metal Festival | Processing test  | true      | available | 1         | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And a booking exists with:
      | buyer_id | event_id | total_price | status     |
      | 2        | 1        | 2000        | processing |
    And I am logged in as a buyer
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 200
    And the response data should include:
      | status    |
      | cancelled |

  Scenario: Cancelled booking releases seats for rebooking
    Given an event exists with:
      | name          | description   | is_active | status    | seller_id | venue_name   | seating_config                                                                      |
      | Limited Event | Only 2 seats  | true      | available | 1         | Taipei Arena | {"rows": 1, "cols": 2, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
    And a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 2000        | pending_payment |
    And I am logged in as a buyer
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 200
    And the response data should include:
      | status    |
      | cancelled |
    When I call POST "/api/booking" with
      | event_id   | section | subsection | seat_selection_mode | seat_positions | quantity |
      | {event_id} | A       | 1          | best_available      | []             | 2        |
    Then the response status code should be 201
    And the response data should include:
      | status     |
      | processing |

  Scenario: Cannot cancel completed booking
    Given an event exists with:
      | name          | description  | is_active | status   | seller_id | venue_name  | seating_config                                                                         |
      | Jazz Festival | Already paid | true      | sold_out | 1         | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1200, "subsections": 1}]} |
    And a booking exists with:
      | buyer_id | event_id | total_price | status    |
      | 2        | 1        | 3000        | completed |
    And I am logged in as a buyer
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 400
    And the error message should contain "Cannot cancel completed booking"
    And the booking status should remain:
      | status    |
      | completed |


  Scenario: Cannot cancel already cancelled booking
    Given an event exists with:
      | name        | description       | is_active | status    | seller_id | venue_name   | seating_config                                                                      |
      | Opera Night | Already cancelled | true      | available | 1         | Taipei Arena | {"rows": 1, "cols": 1, "sections": [{"name": "A", "price": 800, "subsections": 1}]} |
    And I am logged in as a buyer
    And a booking exists with:
      | buyer_id | event_id | total_price | status    |
      | 2        | 1        | 800         | cancelled |
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 400
    And the error message should contain "Booking already cancelled"

  Scenario: Cannot cancel failed booking
    Given an event exists with:
      | name          | description           | is_active | status    | seller_id | venue_name   | seating_config                                                                      |
      | Failed Show   | Reservation failed    | true      | available | 1         | Taipei Arena | {"rows": 1, "cols": 1, "sections": [{"name": "A", "price": 800, "subsections": 1}]} |
    And I am logged in as a buyer
    And a booking exists with:
      | buyer_id | event_id | total_price | status |
      | 2        | 1        | 800         | failed |
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 400
    And the error message should contain "Cannot cancel failed booking"

  Scenario: Only buyer can cancel their own booking
    Given an event exists with:
      | name        | description         | is_active | status    | seller_id | venue_name  | seating_config                                                                         |
      | Pop Concert | Not buyer's booking | true      | available | 1         | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 1500, "subsections": 1}]} |
    And a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 2500        | pending_payment |
    And I am logged in as a buyer with
      | email            | password | name          |
      | another@test.com | P@ssw0rd | Another Buyer |
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 403
    And the error message should contain "Only the buyer can cancel this booking"
    And the booking status should remain:
      | status          |
      | pending_payment |

  Scenario: Seller cannot cancel buyer's booking
    Given an event exists with:
      | name        | description    | is_active | status    | seller_id | venue_name   | seating_config                                                                        |
      | Comedy Show | Seller's event | true      | available | 1         | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "E", "price": 900, "subsections": 1}]} |
    And a booking exists with:
      | buyer_id | event_id | total_price | status          |
      | 2        | 1        | 4000        | pending_payment |
    And I am logged in as a seller
    When I call PATCH "/api/booking/{booking.id}"
    Then the response status code should be 403
    And the error message should contain "Only buyers can perform this action"
    And the booking status should remain:
      | status          |
      | pending_payment |

  Scenario: Cannot cancel non-existent booking for available event
    Given an event exists with:
      | name          | description     | is_active | status    | seller_id | venue_name  | seating_config                                                                         |
      | Dance Concert | Available event | true      | available | 1         | Taipei Dome | {"rows": 30, "cols": 25, "sections": [{"name": "F", "price": 1100, "subsections": 1}]} |
    And I am logged in as a buyer
    When I call PATCH "/api/booking/01900000-0000-7000-8000-000000000000"
    Then the response status code should be 404
    And the error message should contain "Booking not found"
