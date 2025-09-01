Feature: User Creation
  As a system administrator
  I want to create new users
  So that they can access the system

  Scenario: Create a new buyer user
    When I send api
      | email            | password    | first_name | last_name | role  |
      | test@example.com | Test123456! | John       | Doe       | buyer |
    Then the user details should be:
      | email            | password    | first_name | last_name | role  |
      | test@example.com | Test123456! | John       | Doe       | buyer |
    And get 201
      | email            | role  |
      | test@example.com | buyer |
