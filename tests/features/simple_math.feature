Feature: Simple Math

  Scenario: Adding two numbers
    Given I have the number 1
    And I have another number 1
    When I add them together
    Then the result should be 2