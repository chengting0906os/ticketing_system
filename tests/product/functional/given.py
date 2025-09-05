"""Given steps for product BDD tests."""

from fastapi.testclient import TestClient
from pytest_bdd import given


@given('a seller user exists')
def create_seller_user_for_product(step, client: TestClient, product_state):
    """Create a seller user for tests."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    user_data = dict(zip(headers, values, strict=True))
    
    # Create the seller user
    response = client.post('/api/users', json={
        'email': user_data['email'],
        'password': user_data['password'],
        'name': user_data['name'],
        'role': user_data['role'],
    })
    
    assert response.status_code == 201, f"Failed to create seller user: {response.text}"
    created_user = response.json()
    
    # Store the seller_id for use in product creation
    product_state['seller_id'] = created_user['id']
    product_state['seller_user'] = created_user
