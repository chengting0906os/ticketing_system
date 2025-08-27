"""Main conftest importing all step definitions"""

# Import math step definitions explicitly
from tests.steps.math.given import first_number, second_number
from tests.steps.math.then import check_result
from tests.steps.math.when import add_numbers


# Make imported functions available (required for pytest-bdd to find them)
__all__ = [
    'first_number',
    'second_number', 
    'add_numbers',
    'check_result',
]
