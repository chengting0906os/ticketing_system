Feature: Pytest BDD NG Examples
  Examples demonstrating pytest-bdd-ng capabilities

  Scenario: Simple Math - Adding two numbers
    Given I have the number 1
    And I have another number 1
    When I add them together
    Then the result should be 2

  Scenario: DataTable Example
    Given I check step datatable
      | first | second |
      | a     | b      |
