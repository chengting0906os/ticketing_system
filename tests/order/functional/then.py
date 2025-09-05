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


@then('the order status should be "paid"')
def verify_order_status_paid(client: TestClient, order_state):
    response = client.get(f"/api/orders/{order_state['order']['id']}")
    assert response.status_code == 200
    order_data = response.json()
    assert order_data['status'] == 'paid'
    order_state['updated_order'] = order_data


@then('the order should have:')
def verify_order_fields(step, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    
    # Get the updated order if not already fetched
    if 'updated_order' in order_state:
        order_data = order_state['updated_order']
    else:
        order_data = order_state['response'].json()
    
    # Verify order fields
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


@then('the payment should have:')
def verify_payment_details(step, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    
    response_data = order_state['response'].json()
    
    if 'payment_id' in expected_data:
        if expected_data['payment_id'].startswith('PAY_MOCK_'):
            assert response_data.get('payment_id', '').startswith('PAY_MOCK_'), "payment_id should start with PAY_MOCK_"
    if 'status' in expected_data:
        assert response_data.get('status') == expected_data['status'], f"payment status should be {expected_data['status']}"


@then('the product status should be "sold"')
def verify_product_status_sold(client: TestClient, order_state):
    response = client.get(f"/api/products/{order_state['product_id']}")
    assert response.status_code == 200
    product_data = response.json()
    assert product_data['status'] == 'sold'


@then('the product status should be "available"')
def verify_product_status_available(client: TestClient, order_state):
    response = client.get(f"/api/products/{order_state['product_id']}")
    assert response.status_code == 200
    product_data = response.json()
    assert product_data['status'] == 'available'


@then('the error message should contain "Order already paid"')
def verify_error_order_already_paid(order_state):
    response = order_state['response']
    assert response.status_code == 400
    error_data = response.json()
    assert 'Order already paid' in error_data['detail']


@then('the error message should contain "Cannot pay for cancelled order"')
def verify_error_cannot_pay_cancelled(order_state):
    response = order_state['response']
    assert response.status_code == 400
    error_data = response.json()
    assert 'Cannot pay for cancelled order' in error_data['detail']


@then('the error message should contain "Only the buyer can pay for this order"')
def verify_error_only_buyer_can_pay(order_state):
    response = order_state['response']
    assert response.status_code == 403
    error_data = response.json()
    assert 'Only the buyer can pay for this order' in error_data['detail']


@then('the order status should be "cancelled"')
def verify_order_status_cancelled(client: TestClient, order_state):
    response = client.get(f"/api/orders/{order_state['order']['id']}")
    assert response.status_code == 200
    order_data = response.json()
    assert order_data['status'] == 'cancelled'
    order_state['updated_order'] = order_data


@then('the error message should contain "Cannot cancel paid order"')
def verify_error_cannot_cancel_paid(order_state):
    response = order_state['response']
    assert response.status_code == 400
    error_data = response.json()
    assert 'Cannot cancel paid order' in error_data['detail']
