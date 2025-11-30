from typing import Any

from pytest_bdd import when


@when('I add them together')
def add_numbers(calculator_state: dict[str, Any]) -> None:
    calculator_state['result'] = sum(calculator_state['numbers'])
