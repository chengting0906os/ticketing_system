"""Then steps for order BDD tests."""


from fastapi.testclient import TestClient
from pytest_bdd import then


@then('the order should be created with:')
def verify_order_created(step, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    
    response = order_state['response']
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    
    order_data = response.json()
    
    # Verify order fields
    if 'price' in expected_data:
        assert order_data['price'] == int(expected_data['price'])
    if 'status' in expected_data:
        assert order_data['status'] == expected_data['status']
    if 'created_at' in expected_data:
        if expected_data['created_at'] == 'not_null':
            assert order_data.get('created_at') is not None, "created_at should not be null"
        elif expected_data['created_at'] == 'null':
            assert order_data.get('created_at') is None, "created_at should be null"
    if 'paid_at' in expected_data:
        if expected_data['paid_at'] == 'null':
            assert order_data.get('paid_at') is None, "paid_at should be null"
        elif expected_data['paid_at'] == 'not_null':
            assert order_data.get('paid_at') is not None, "paid_at should not be null"
    
    order_state['created_order'] = order_data


@then('the product status should be "reserved"')
def verify_product_status_reserved(client: TestClient, order_state):
    # Get the updated product status
    product_id = order_state['product']['id']
    response = client.get(f'/api/products/{product_id}')
    
    assert response.status_code == 200
    updated_product = response.json()
    assert updated_product['status'] == 'reserved'


@then('the error message should contain "Product not available"')
def verify_error_product_not_available(order_state):
    response = order_state['response']
    assert response.status_code == 400
    error_data = response.json()
    assert 'Product not available' in error_data['detail']


@then('the error message should contain "Product not active"')
def verify_error_product_not_active(order_state):
    response = order_state['response']
    assert response.status_code == 400
    error_data = response.json()
    assert 'Product not active' in error_data['detail']


@then('the error message should contain "Only buyers can create orders"')
def verify_error_only_buyers_can_create_orders(order_state):
    response = order_state['response']
    assert response.status_code == 403
    error_data = response.json()
    assert 'Only buyers can create orders' in error_data['detail']
