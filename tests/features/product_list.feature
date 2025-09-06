Feature: Product List
  As a seller
  I can see all of my products

  As a buyer
  I only can see available products

  Scenario: Seller sees all their products
    Given a seller with products:
      | name      | description        | price | is_active | status    |
      | Product A | Active available   |  1000 | true      | available |
      | Product B | Inactive available |  2000 | false     | available |
      | Product C | Active reserved    |  3000 | true      | reserved  |
      | Product D | Active sold        |  4000 | true      | sold      |
      | Product E | Active available   |  1000 | true      | available |
    When the seller requests their products
    Then the seller should see 5 products
    And the products should include all statuses

  Scenario: Buyer sees only active and available products
    Given a seller with products:
      | name      | description        | price | is_active | status    |
      | Product A | Active available   |  1000 | true      | available |
      | Product B | Inactive available |  2000 | false     | available |
      | Product C | Active reserved    |  3000 | true      | reserved  |
      | Product D | Active sold        |  4000 | true      | sold      |
      | Product E | Active available   |  1000 | true      | available |
    When a buyer requests products
    Then the buyer should see 2 products
    And the products should be:
      | name      | description      | price | is_active | status    |
      | Product A | Active available |  1000 | true      | available |
      | Product E | Active available |  1000 | true      | available |

  Scenario: Empty product list
    Given no available products exist
      | name      | description     | price | is_active | status   |
      | Product C | Active reserved |  3000 | true      | reserved |
      | Product D | Active sold     |  4000 | true      | sold     |
    When a buyer requests products
    Then the buyer should see 0 products
