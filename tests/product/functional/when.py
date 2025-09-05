"""When steps for product BDD tests."""

from fastapi.testclient import TestClient
from pytest_bdd import when


@when('I create a product with')
def create_product(step, client: TestClient, product_state):
    """Create a product with the given data."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    row_data = dict(zip(headers, values, strict=True))
    
    # Get seller_id from test data or from product_state (created by Background)
    if 'seller_id' in row_data:
        seller_id = int(row_data['seller_id'])
    else:
        seller_id = product_state.get('seller_id')
        if not seller_id:
            raise ValueError("No seller_id found. Make sure a seller user is created first or provide it in test data.")
    
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'seller_id': seller_id,
    }
    
    # Add is_active if specified in the test data
    if 'is_active' in row_data:
        request_data['is_active'] = row_data['is_active'].lower() == 'true'
    
    product_state['request_data'] = request_data
    
    product_state['response'] = client.post('/api/products', json=product_state['request_data'])


@when('I update the product to')
def update_product(step, client: TestClient, product_state):
    """Update a product with the given data."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    update_data = dict(zip(headers, values, strict=True))
    
    # Convert data types
    if 'price' in update_data:
        update_data['price'] = int(update_data['price'])
    if 'is_active' in update_data:
        update_data['is_active'] = update_data['is_active'].lower() == 'true'
    
    product_id = product_state['product_id']
    product_state['update_data'] = update_data
    
    # Send PATCH request to update product
    product_state['response'] = client.patch(f'/api/products/{product_id}', json=update_data)
