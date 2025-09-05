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
    
    # Use seller_id from product_state (created by Background)
    seller_id = product_state.get('seller_id')
    if not seller_id:
        raise ValueError("No seller_id found. Make sure a seller user is created first.")
    
    product_state['request_data'] = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'seller_id': str(seller_id),  # Convert UUID to string for JSON serialization
    }
    
    product_state['response'] = client.post('/api/products', json=product_state['request_data'])
