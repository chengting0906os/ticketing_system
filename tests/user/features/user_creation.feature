Feature: User Creation
  As a system administrator
  I want to create new users
  So that they can access the system

  Scenario: Create a new buyer user
    When I send api
      | email            | password | name     | role  |
      | test@example.com | P@ssw0rd | John Doe | buyer |
    Then the user details should be:
      | email            | password | name     | role  |
      | test@example.com | P@ssw0rd | John Doe | buyer |
    And the response status code should be:
      | 201 |

  Scenario: Create a new seller user
    When I send api
      | email            | password | name | role   |
      | test@example.com | P@ssw0rd | Ryan | seller |
    Then the seller user details should be:
      | email            | password | name | role   |
      | test@example.com | P@ssw0rd | Ryan | seller |
    And the response status code should be:
      | 201 |

  Scenario: Create a new wrong user
    When I send api
      | email            | password | name | role       |
      | test@example.com | P@ssw0rd | Max  | wrong_user |
    Then the wrong user details should be:
      | email            | password | name | role       |
      | test@example.com | P@ssw0rd | Max  | wrong_user |
    And the response status code should be:
      | 400 |
