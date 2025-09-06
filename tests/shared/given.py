"""Shared test steps for authentication."""

from pytest_bdd import given


@given('I am logged in as:')
def login_user_with_table(step, client):
    """Login user using data table."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    login_data = dict(zip(headers, values, strict=True))
    
    response = client.post(
        "/api/auth/login",
        data={"username": login_data['email'], "password": login_data['password']},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    # Custom login endpoint returns 200 with user data
    assert response.status_code == 200, f"Login failed: {response.text}"
    
    # Store the cookie for subsequent requests
    if 'fastapiusersauth' in response.cookies:
        client.cookies.set('fastapiusersauth', response.cookies['fastapiusersauth'])
    
    return response
