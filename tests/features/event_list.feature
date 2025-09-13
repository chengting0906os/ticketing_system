Feature: Event List
  As a seller
  I can see all of my events

  As a buyer
  I only can see available events

  Scenario: Seller sees all their events
    Given a seller with events:
      | name    | description        | price | is_active | status    | venue_name   | seating_config                                                                                 |
      | Event A | Active available   |  1000 | true      | available | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
      | Event B | Inactive available |  2000 | false     | available | Taipei Dome  | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
      | Event C | Active reserved    |  3000 | true      | reserved  | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
      | Event D | Active sold        |  4000 | true      | sold      | Taipei Dome  | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
      | Event E | Active available   |  1000 | true      | available | Taipei Arena | {"sections": [{"name": "E", "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]} |
    When the seller requests their events
    Then the seller should see 5 events
    And the events should include all statuses

  Scenario: Buyer sees only active and available events
    Given a seller with events:
      | name    | description        | price | is_active | status    | venue_name   | seating_config                                                                                 |
      | Event A | Active available   |  1000 | true      | available | Taipei Arena | {"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]} |
      | Event B | Inactive available |  2000 | false     | available | Taipei Dome  | {"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]} |
      | Event C | Active reserved    |  3000 | true      | reserved  | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
      | Event D | Active sold        |  4000 | true      | sold      | Taipei Dome  | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
      | Event E | Active available   |  1000 | true      | available | Taipei Arena | {"sections": [{"name": "E", "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]} |
    When a buyer requests events
    Then the buyer should see 2 events
    And the events should be:
      | name    | description      | price | is_active | status    |
      | Event A | Active available |  1000 | true      | available |
      | Event E | Active available |  1000 | true      | available |

  Scenario: Empty event list
    Given no available events exist
      | name    | description     | price | is_active | status   | venue_name   | seating_config                                                                                 |
      | Event C | Active reserved |  3000 | true      | reserved | Taipei Arena | {"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]} |
      | Event D | Active sold     |  4000 | true      | sold     | Taipei Dome  | {"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]} |
    When a buyer requests events
    Then the buyer should see 0 events
