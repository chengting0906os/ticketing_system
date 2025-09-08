from pytest_bdd import when


@when('I add them together')
def add_numbers(calculator_state):
    calculator_state['result'] = sum(calculator_state['numbers'])
