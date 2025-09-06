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


@then('the order status should be "cancelled"')
def verify_order_status_cancelled(client: TestClient, order_state):
    response = client.get(f"/api/orders/{order_state['order']['id']}")
    assert response.status_code == 200
    order_data = response.json()
    assert order_data['status'] == 'cancelled'
    order_state['updated_order'] = order_data



@then('the response should contain 3 orders')
def verify_3_orders(order_state):
    response = order_state['response']
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 3, f"Expected 3 orders, got {len(orders)}"
    order_state['orders_response'] = orders


@then('the response should contain 2 orders')
def verify_2_orders(order_state):
    response = order_state['response']
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2, f"Expected 2 orders, got {len(orders)}"
    order_state['orders_response'] = orders


@then('the response should contain 1 order')
def verify_1_order(order_state):
    response = order_state['response']
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 1, f"Expected 1 order, got {len(orders)}"
    order_state['orders_response'] = orders


@then('the response should contain 0 orders')
def verify_0_orders(order_state):
    response = order_state['response']
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 0, f"Expected 0 orders, got {len(orders)}"
    order_state['orders_response'] = orders


@then('the orders should include:')
def verify_orders_details(step, order_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    orders = order_state['orders_response']
    
    for _, row in enumerate(rows[1:]):
        values = [cell.value for cell in row.cells]
        expected_data = dict(zip(headers, values, strict=True))
        
        # Find the order with matching ID
        order_id = int(expected_data['id'])
        order = next((o for o in orders if o['id'] == order_id), None)
        assert order is not None, f"Order with id {order_id} not found in response"
        
        # Verify fields
        if 'product_name' in expected_data:
            assert order.get('product_name') == expected_data['product_name']
        if 'price' in expected_data:
            assert order.get('price') == int(expected_data['price'])
        if 'status' in expected_data:
            assert order.get('status') == expected_data['status']
        if 'seller_name' in expected_data:
            assert order.get('seller_name') == expected_data['seller_name']
        if 'buyer_name' in expected_data:
            assert order.get('buyer_name') == expected_data['buyer_name']
        if 'created_at' in expected_data:
            if expected_data['created_at'] == 'not_null':
                assert order.get('created_at') is not None
        if 'paid_at' in expected_data:
            if expected_data['paid_at'] == 'not_null':
                assert order.get('paid_at') is not None
            elif expected_data['paid_at'] == 'null':
                assert order.get('paid_at') is None


@then('all orders should have status "paid"')
def verify_all_orders_status_paid(order_state):
    orders = order_state['orders_response']
    for order in orders:
        assert order.get('status') == 'paid', f"Order {order['id']} has status {order.get('status')}, expected paid"


@then('all orders should have status "pending_payment"')
def verify_all_orders_status_pending(order_state):
    orders = order_state['orders_response']
    for order in orders:
        assert order.get('status') == 'pending_payment', f"Order {order['id']} has status {order.get('status')}, expected pending_payment"


@then('all orders should have status "cancelled"')
def verify_all_orders_status_cancelled(order_state):
    orders = order_state['orders_response']
    for order in orders:
        assert order.get('status') == 'cancelled', f"Order {order['id']} has status {order.get('status')}, expected cancelled"


