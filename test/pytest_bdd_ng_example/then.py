from typing import Any

from pytest_bdd import then


@then('the result should be 2')
def verify_result(calculator_state: dict[str, Any]) -> None:
    assert calculator_state['result'] == 2
