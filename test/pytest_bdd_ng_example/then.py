from pytest_bdd import then


@then('the result should be 2')
def verify_result(calculator_state):
    assert calculator_state['result'] == 2
