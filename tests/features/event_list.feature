Feature: Event List
  As a seller
  I can see all of my events

  As a buyer
  I only can see available events

  Scenario: Seller sees all their events
    Given a seller with events:
      | name      | description        | price | is_active | status    |
      | Event A | Active available   |  1000 | true      | available |
      | Event B | Inactive available |  2000 | false     | available |
      | Event C | Active reserved    |  3000 | true      | reserved  |
      | Event D | Active sold        |  4000 | true      | sold      |
      | Event E | Active available   |  1000 | true      | available |
    When the seller requests their events
    Then the seller should see 5 events
    And the events should include all statuses

  Scenario: Buyer sees only active and available events
    Given a seller with events:
      | name      | description        | price | is_active | status    |
      | Event A | Active available   |  1000 | true      | available |
      | Event B | Inactive available |  2000 | false     | available |
      | Event C | Active reserved    |  3000 | true      | reserved  |
      | Event D | Active sold        |  4000 | true      | sold      |
      | Event E | Active available   |  1000 | true      | available |
    When a buyer requests events
    Then the buyer should see 2 events
    And the events should be:
      | name      | description      | price | is_active | status    |
      | Event A | Active available |  1000 | true      | available |
      | Event E | Active available |  1000 | true      | available |

  Scenario: Empty event list
    Given no available events exist
      | name      | description     | price | is_active | status   |
      | Event C | Active reserved |  3000 | true      | reserved |
      | Event D | Active sold     |  4000 | true      | sold     |
    When a buyer requests events
    Then the buyer should see 0 events
