"""Math step definitions for pytest-bdd-ng examples."""

from pytest_bdd import given, when, then


class MathState:
    """Shared state for math scenarios."""
    numbers = []
    result = None
    
    @classmethod
    def reset(cls):
        cls.numbers = []
        cls.result = None


@given('I have the number 1')
def first_number():
    MathState.reset()  # Reset for each scenario
    MathState.numbers.append(1)


@given('I have another number 1')  
def second_number():
    MathState.numbers.append(1)


@when('I add them together')
def add_numbers():
    MathState.result = sum(MathState.numbers)


@then('the result should be 2')
def check_result():
    assert MathState.result == 2