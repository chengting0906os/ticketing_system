Feature: User Management
  As a system administrator
  I want to manage users through the API
  So that users can register and use the system

  Background:
    Given the API endpoint "/api/user"

  Scenario: Register as organizer
    When I call the API with:
      | endpoint | method | email             | password | first_name | last_name | role      |
      | /users   | POST   | alice@example.com | Pass123! | Alice      | Chen      | organizer |
    Then the response should be:
      | status_code | user.id | user.email        | user.role |
      | 201         | 1       | alice@example.com | organizer |

  Scenario: Register as customer
    When I call the API with:
      | endpoint | method | email           | password | first_name | last_name | role     |
      | /users   | POST   | bob@example.com | Pass456! | Bob        | Smith     | customer |
    Then the response should be:
      | status_code | user.id | user.email      | user.role |
      | 201         | 2       | bob@example.com | customer  |

  Scenario: Duplicate email registration fails
    Given a User exists with:
      | id | email             | first_name | last_name |
      | 1  | alice@example.com | Alice      | Chen      |
    When I call the API with:
      | endpoint | method | email             | password | first_name | last_name |
      | /users   | POST   | alice@example.com | Pass456! | Alice      | Wang      |
    Then the request should fail with message "Email already exists"

