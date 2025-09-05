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
