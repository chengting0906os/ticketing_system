@integration
Feature: Event List
  As a seller
  I can see all of my events

  As a buyer
  I only can see open events

  Scenario: Seller sees all their events
    Given a seller with events:
      | name          | description        | is_active | status    | venue_name   | seating_config                                                                                                |
      | Rock Concert  | Active open   | true      | open | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
      | Jazz Festival | Inactive open | false     | open | Taipei Dome  | {"sections": [{"name": "B", "price": 1200, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
      | Opera Night   | Active completed   | true      | completed | Taipei Arena | {"sections": [{"name": "C", "price": 800, "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]}  |
      | Pop Concert   | Active sold_out    | true      | sold_out  | Taipei Dome  | {"sections": [{"name": "D", "price": 1500, "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
      | Comedy Show   | Active open   | true      | open | Taipei Arena | {"sections": [{"name": "E", "price": 900, "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]}  |
    When the seller requests their events
    Then the seller should see 5 events
    And the events should include all statuses

  Scenario: Buyer sees only active and open events
    Given a seller with events:
      | name          | description        | is_active | status    | venue_name   | seating_config                                                                                                |
      | Rock Concert  | Active open   | true      | open | Taipei Arena | {"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
      | Jazz Festival | Inactive open | false     | open | Taipei Dome  | {"sections": [{"name": "B", "price": 1200, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
      | Opera Night   | Active completed   | true      | completed | Taipei Arena | {"sections": [{"name": "C", "price": 800, "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]}  |
      | Pop Concert   | Active sold_out    | true      | sold_out  | Taipei Dome  | {"sections": [{"name": "D", "price": 1500, "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
      | Comedy Show   | Active open   | true      | open | Taipei Arena | {"sections": [{"name": "E", "price": 900, "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]}  |
    When a buyer requests events
    Then the buyer should see 2 events
    And the events should be:
      | name         | description      | is_active | status    |
      | Rock Concert | Active open | true      | open |
      | Comedy Show  | Active open | true      | open |

  Scenario: Empty event list
    Given no open events exist
      | name        | description     | is_active | status   | venue_name   | seating_config                                                                                                |
      | Opera Night | Active ended    | true      | ended    | Taipei Arena | {"sections": [{"name": "C", "price": 800, "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]}  |
      | Pop Concert | Active sold_out | true      | sold_out | Taipei Dome  | {"sections": [{"name": "D", "price": 1500, "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    When a buyer requests events
    Then the buyer should see 0 events
