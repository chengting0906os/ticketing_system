@integration
Feature: User Creation
  As a system administrator
  I want to create new users
  So that they can access the system

  @smoke
  Scenario: Create a new buyer user
    When I call POST "/api/user" with
      | email            | password | name     | role  |
      | test@example.com | P@ssw0rd | John Doe | buyer |
    Then the response status code should be 201
    And the response data should include:
      | email            | name     | role  |
      | test@example.com | John Doe | buyer |

  Scenario: Create a new seller user
    When I call POST "/api/user" with
      | email            | password | name | role   |
      | test@example.com | P@ssw0rd | Ryan | seller |
    Then the response status code should be 201
    And the response data should include:
      | email            | name | role   |
      | test@example.com | Ryan | seller |

  Scenario: Create a new wrong user
    When I call POST "/api/user" with
      | email            | password | name | role       |
      | test@example.com | P@ssw0rd | Max  | wrong_user |
    Then the response status code should be 400
    And the error message should contain "Input should be"
