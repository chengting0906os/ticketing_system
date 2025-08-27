"""Math Given step definitions"""
from pytest_bdd import given
from .shared import MathState


@given('I have the number 1')
def first_number():
    MathState.reset()  # Reset for each scenario
    MathState.numbers.append(1)


@given('I have another number 1')  
def second_number():
    MathState.numbers.append(1)
