@integration
Feature: User Login
  As a registered user
  I want to login to the system
  So that I can access protected resources

  Background:
    Given a buyer exists
    And a seller exists

  @smoke
  Scenario: Successful buyer login
    When I call POST "/api/user/login" with
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    Then the login response should be successful
    And the response status code should be 200
    And the response should contain a JWT cookie
    And the response data should include:
      | email          | name       | role  |
      | buyer@test.com | Test Buyer | buyer |

  Scenario: Successful seller login
    When I call POST "/api/user/login" with
      | email           | password |
      | seller@test.com | P@ssw0rd |
    Then the login response should be successful
    And the response status code should be 200
    And the response should contain a JWT cookie
    And the response data should include:
      | email           | name        | role   |
      | seller@test.com | Test Seller | seller |

  Scenario: Login with wrong password should return 400
    When I call POST "/api/user/login" with
      | email          | password  |
      | buyer@test.com | WrongPass |
    Then the login response should fail
    And the response status code should be 400
    And the error message should contain "LOGIN_BAD_CREDENTIALS"

  Scenario: Login with non-existent email should return 400
    When I call POST "/api/user/login" with
      | email             | password |
      | nonexist@test.com | P@ssw0rd |
    Then the login response should fail
    And the response status code should be 400
    And the error message should contain "LOGIN_BAD_CREDENTIALS"

  Scenario: Login with empty credentials should return 400
    When I call POST "/api/user/login" with
      | email | password |
      |       |          |
    Then the login response should fail
    And the response status code should be 400
    And the error message should contain "valid email"
