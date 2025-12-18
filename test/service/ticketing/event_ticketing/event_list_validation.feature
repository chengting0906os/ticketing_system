@integration
Feature: Event List
  As a seller
  I can see all of my events

  As a buyer
  I only can see available events

  Scenario: Seller sees all their events
    Given a seller with events:
      | name          | description        | is_active | status    | venue_name   | seating_config                                                               |
      | Rock Concert  | Active available   | true      | available | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
      | Jazz Festival | Inactive available | false     | available | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1200, "subsections": 1}]} |
      | Opera Night   | Active completed   | true      | completed | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "C", "price": 800, "subsections": 1}]}  |
      | Pop Concert   | Active sold_out    | true      | sold_out  | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 1500, "subsections": 1}]} |
      | Comedy Show   | Active available   | true      | available | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "E", "price": 900, "subsections": 1}]}  |
    When I call GET "/api/event?seller_id={seller_id}"
    Then the seller should see 5 events
    And the events should include all statuses

  @smoke
  Scenario: Buyer sees only active and available events
    Given a seller with events:
      | name          | description        | is_active | status    | venue_name   | seating_config                                                               |
      | Rock Concert  | Active available   | true      | available | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]} |
      | Jazz Festival | Inactive available | false     | available | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1200, "subsections": 1}]} |
      | Opera Night   | Active completed   | true      | completed | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "C", "price": 800, "subsections": 1}]}  |
      | Pop Concert   | Active sold_out    | true      | sold_out  | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 1500, "subsections": 1}]} |
      | Comedy Show   | Active available   | true      | available | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "E", "price": 900, "subsections": 1}]}  |
    When I call GET "/api/event"
    Then the buyer should see 2 events
    And the events should be:
      | name         | description      | is_active | status    |
      | Rock Concert | Active available | true      | available |
      | Comedy Show  | Active available | true      | available |

  Scenario: Empty event list
    Given no available events exist
      | name        | description     | is_active | status   | venue_name   | seating_config                                                              |
      | Opera Night | Active ended    | true      | ended    | Taipei Arena | {"rows": 25, "cols": 20, "sections": [{"name": "C", "price": 800, "subsections": 1}]}  |
      | Pop Concert | Active sold_out | true      | sold_out | Taipei Dome  | {"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 1500, "subsections": 1}]} |
    When I call GET "/api/event"
    Then the buyer should see 0 events
