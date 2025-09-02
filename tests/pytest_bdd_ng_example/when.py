"""When steps for pytest_bdd_ng features."""

from pytest_bdd import when


@when('I add them together')
def add_numbers(calculator_state):
    """Add all numbers together."""
    calculator_state['result'] = sum(calculator_state['numbers'])
