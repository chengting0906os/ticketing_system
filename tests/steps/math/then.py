"""Math Then step definitions"""
from pytest_bdd import then
from .shared import MathState


@then('the result should be 2')
def check_result():
    assert MathState.result == 2
