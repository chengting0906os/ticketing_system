"""When steps for order BDD tests."""

from fastapi.testclient import TestClient
from pytest_bdd import when


@when('the buyer creates an order for the product')
def buyer_creates_order(client: TestClient, order_state):
    response = client.post('/api/orders', json={
        'buyer_id': order_state['buyer']['id'],
        'product_id': order_state['product']['id']
    })
    
    order_state['response'] = response


@when('the buyer tries to create an order for the product')
def buyer_tries_to_create_order(client: TestClient, order_state):
    response = client.post('/api/orders', json={
        'buyer_id': order_state['buyer']['id'],
        'product_id': order_state['product']['id']
    })
    
    order_state['response'] = response


@when('the seller tries to create an order for their own product')
def seller_tries_to_create_order(client: TestClient, order_state):
    response = client.post('/api/orders', json={
        'buyer_id': order_state['seller']['id'],
        'product_id': order_state['product']['id']
    })
    
    order_state['response'] = response


@when('the buyer pays for the order with:')
def buyer_pays_for_order(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    payment_data = dict(zip(headers, values, strict=True))
    
    response = client.post(f"/api/orders/{order_state['order']['id']}/pay", json={
        'card_number': payment_data['card_number'],
        'buyer_id': order_state['buyer_id']
    })
    
    order_state['response'] = response


@when('the buyer tries to pay for the order again')
def buyer_tries_to_pay_again(client: TestClient, order_state):
    response = client.post(f"/api/orders/{order_state['order']['id']}/pay", json={
        'card_number': '4242424242424242',
        'buyer_id': order_state['buyer_id']
    })
    
    order_state['response'] = response


@when('the buyer tries to pay for the order')
def buyer_tries_to_pay(client: TestClient, order_state):
    response = client.post(f"/api/orders/{order_state['order']['id']}/pay", json={
        'card_number': '4242424242424242',
        'buyer_id': order_state['buyer_id']
    })
    
    order_state['response'] = response


@when('another user tries to pay for the order')
def another_user_tries_to_pay(client: TestClient, order_state):
    # Create another buyer
    another_buyer_response = client.post('/api/users', json={
        'email': 'another_buyer@test.com',
        'password': 'password123',
        'name': 'Another Buyer',
        'role': 'buyer',
    })
    
    if another_buyer_response.status_code == 201:
        another_buyer_id = another_buyer_response.json()['id']
    else:
        another_buyer_id = 999  # Use a different ID
    
    response = client.post(f"/api/orders/{order_state['order']['id']}/pay", json={
        'card_number': '4242424242424242',
        'buyer_id': another_buyer_id
    })
    
    order_state['response'] = response


@when('the buyer cancels the order')
def buyer_cancels_order(client: TestClient, order_state):
    response = client.delete(f"/api/orders/{order_state['order']['id']}?buyer_id={order_state['buyer_id']}")
    
    order_state['response'] = response


@when('the buyer tries to cancel the order')
def buyer_tries_to_cancel(client: TestClient, order_state):
    response = client.delete(f"/api/orders/{order_state['order']['id']}?buyer_id={order_state['buyer_id']}")
    
    order_state['response'] = response


@when('buyer with id 3 requests their orders')
def buyer_3_requests_orders(client: TestClient, order_state):
    response = client.get("/api/orders/buyer/3")
    order_state['response'] = response


@when('buyer with id 4 requests their orders')
def buyer_4_requests_orders(client: TestClient, order_state):
    response = client.get("/api/orders/buyer/4")
    order_state['response'] = response


@when('buyer with id 5 requests their orders')
def buyer_5_requests_orders(client: TestClient, order_state):
    response = client.get("/api/orders/buyer/5")
    order_state['response'] = response


@when('seller with id 1 requests their orders')
def seller_1_requests_orders(client: TestClient, order_state):
    response = client.get("/api/orders/seller/1")
    order_state['response'] = response


@when('buyer with id 3 requests their orders with status "paid"')
def buyer_3_requests_orders_paid(client: TestClient, order_state):
    response = client.get("/api/orders/buyer/3?order_status=paid")
    order_state['response'] = response


@when('buyer with id 3 requests their orders with status "pending_payment"')
def buyer_3_requests_orders_pending(client: TestClient, order_state):
    response = client.get("/api/orders/buyer/3?order_status=pending_payment")
    order_state['response'] = response
