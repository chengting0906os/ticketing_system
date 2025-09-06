Feature: User Login
  As a registered user
  I want to login to the system
  So that I can access protected resources

  Background:
    Given a buyer user exists
      | email          | password | name     | role  |
      | buyer@test.com | P@ssw0rd | John Doe | buyer |
    And a seller user exists
      | email           | password | name | role   |
      | seller@test.com | P@ssw0rd | Ryan | seller |

  Scenario: Successful buyer login
    When I login with
      | email          | password |
      | buyer@test.com | P@ssw0rd |
    Then the login response should be successful
    And get 200
    And the response should contain a JWT cookie
    And the user info should be
      | email          | name     | role  |
      | buyer@test.com | John Doe | buyer |

  Scenario: Successful seller login
    When I login with
      | email           | password |
      | seller@test.com | P@ssw0rd |
    Then the login response should be successful
    And get 200
    And the response should contain a JWT cookie
    And the user info should be
      | email           | name | role   |
      | seller@test.com | Ryan | seller |
