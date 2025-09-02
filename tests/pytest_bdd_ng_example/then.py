"""Then steps for pytest_bdd_ng features."""

from pytest_bdd import then


@then('the result should be 2')
def verify_result(calculator_state):
    """Verify the addition result."""
    assert calculator_state['result'] == 2
