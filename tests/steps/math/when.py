"""Math When step definitions"""
from pytest_bdd import when
from .shared import MathState


@when('I add them together')
def add_numbers():
    MathState.result = sum(MathState.numbers)
