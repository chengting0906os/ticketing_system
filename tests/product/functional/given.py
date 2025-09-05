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


@given('a product exists')
def product_exists(step, client: TestClient, product_state):
    """Create a product for testing updates."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    row_data = dict(zip(headers, values, strict=True))
    
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'seller_id': int(row_data['seller_id']),
        'is_active': row_data['is_active'].lower() == 'true'
    }
    
    response = client.post('/api/products', json=request_data)
    assert response.status_code == 201, f"Failed to create product: {response.text}"
    
    product_data = response.json()
    product_state['product_id'] = product_data['id']
    product_state['original_product'] = product_data
    product_state['request_data'] = request_data
