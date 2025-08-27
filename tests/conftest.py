"""Main conftest importing all step definitions"""

# Import user step definitions explicitly
from tests.steps.user.given import setup_database
from tests.steps.user.when import create_user
from tests.steps.user.then import (
    check_user_saved, 
    check_user_email,
    check_user_details_with_table
)

# Import pytest-bdd-ng test steps
from tests.steps.pytest_bdd_ng.test_steps import check_datatable
from tests.steps.pytest_bdd_ng.math_steps import (
    first_number,
    second_number,
    add_numbers,
    check_result
)


# Make imported functions available (required for pytest-bdd to find them)
__all__ = [
    # User steps
    'setup_database',
    'create_user',
    'check_user_saved',
    'check_user_email',
    'check_user_details_with_table',
    # pytest-bdd-ng steps
    'check_datatable',
    'first_number',
    'second_number',
    'add_numbers',
    'check_result',
]
