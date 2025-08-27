"""User When step definitions."""

import uuid

from messages import Step
from pytest_bdd import when

from src.user.domain.user_model import User
from tests.steps.user.shared import UserState


def get_datatable_row_values(row):
    """Extract values from a DataTable row."""
    return list(map(lambda cell: cell.value, row.cells))


@when('I create a user with the following details:')
def create_user(step: Step):
    """Create a user with provided details."""
    # Extract headers and data from data table
    if step.data_table is None:
        raise ValueError("No data table provided in step")
    
    title_row, *data_rows = step.data_table.rows
    headers = get_datatable_row_values(title_row)
    values = get_datatable_row_values(data_rows[0])
    
    # Create dictionary from headers and values
    user_data = dict(zip(headers, values, strict=True))
    
    UserState.user_data = user_data
    
    # Create user object
    user = User(
        id=uuid.uuid4(),
        email=user_data['email'],
        hashed_password=UserState.hash_password(user_data['password']),
        first_name=user_data['first_name'],
        last_name=user_data['last_name'],
        role=user_data['role'],
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    
    # Save to database
    if UserState.session is not None:
        UserState.session.add(user)
        UserState.session.commit()
        UserState.created_user = user
    else:
        raise RuntimeError("Database session not initialized")
