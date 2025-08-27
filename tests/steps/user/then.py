"""User Then step definitions."""

from messages import Step
from pytest_bdd import parsers, then

from src.user.domain.user_model import User
from tests.steps.user.shared import UserState


@then('the user should be saved in the database')
def check_user_saved():
    """Check if user is saved in database."""
    if UserState.session is None:
        raise RuntimeError("Database session not initialized")
    
    # Query the database to verify user exists
    saved_user = UserState.session.query(User).filter_by(
        email=UserState.user_data['email']
    ).first()
    
    assert saved_user is not None, "User was not saved to database"
    assert saved_user.email == UserState.user_data['email']


@then(parsers.parse('the user email should be "{expected_email}"'))
def check_user_email(expected_email):
    """Verify user email."""
    assert UserState.created_user is not None, "No user was created"
    assert UserState.created_user.email == expected_email


@then('the user details should be:')
def check_user_details_with_table(step: Step):
    """Verify user details using a data table."""
    assert UserState.created_user is not None, "No user was created"
    assert step.data_table is not None, "No data table provided"
    
    # Get header and data rows
    header_row = step.data_table.rows[0]
    data_row = step.data_table.rows[1]
    
    # Extract headers and values
    headers = [cell.value for cell in header_row.cells]
    values = [cell.value for cell in data_row.cells]
    
    # Create a dictionary from headers and values
    expected_details = dict(zip(headers, values, strict=False))
    
    # Verify each field
    for field, expected_value in expected_details.items():
        actual_value = getattr(UserState.created_user, field)
        assert actual_value == expected_value, f"User {field} mismatch: expected {expected_value}, got {actual_value}"
