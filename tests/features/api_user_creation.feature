Feature: User Creation
  As a system administrator
  I want to create new users
  So that they can access the system

  Scenario: Create a new buyer userddasd
    Given I have a database connection
    When I create a user with the following details:
      | email            | password    | first_name | last_name | role  |
      | test@example.com | Test123456! | John       | Doe       | buyer |
    Then the user should be saved in the database
    And the user details should be:
      | email            | role  |
      | test@example.com | buyer |

  Scenario Outline: Create users with different roles
    Given I have a database connection
    When I create a user with the following details:
      | email   | password   | first_name   | last_name   | role   |
      | <email> | <password> | <first_name> | <last_name> | <role> |
    Then the user should be saved in the database
    And the user details should be:
      | email   | role   |
      | <email> | <role> |

    Examples:
      | email              | password    | first_name | last_name | role   |
      | buyer1@example.com | Buy123456!  | Alice      | Buyer     | buyer  |
      | seller@example.com | Sell123456! | Bob        | Seller    | seller |
      | buyer2@example.com | Buy223456!  | Charlie    | Buyer     | buyer  |
