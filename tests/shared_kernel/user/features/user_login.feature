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
    And the response status code should be:
      | 200 |
    And the response should contain a JWT cookie
    And the user info should be
      | email          | name     | role  |
      | buyer@test.com | John Doe | buyer |

  Scenario: Successful seller login
    When I login with
      | email           | password |
      | seller@test.com | P@ssw0rd |
    Then the login response should be successful
    And the response status code should be:
      | 200 |
    And the response should contain a JWT cookie
    And the user info should be
      | email           | name | role   |
      | seller@test.com | Ryan | seller |

  Scenario: Login with wrong password should return 400
    When I login with
      | email          | password  |
      | buyer@test.com | WrongPass |
    Then the login response should fail
    And the response status code should be:
      | 400 |
    And the error message should contain:
      | LOGIN_BAD_CREDENTIALS |

  Scenario: Login with non-existent email should return 400
    When I login with
      | email             | password |
      | nonexist@test.com | P@ssw0rd |
    Then the login response should fail
    And the response status code should be:
      | 400 |
    And the error message should contain:
      | LOGIN_BAD_CREDENTIALS |

  Scenario: Login with empty credentials should return 400
    When I login with
      | email | password |
      |       |          |
    Then the login response should fail
    And the response status code should be:
      | 400 |
    And the error message should contain:
      | LOGIN_BAD_CREDENTIALS |
