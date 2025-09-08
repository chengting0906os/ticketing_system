from fastapi.testclient import TestClient
from pytest_bdd import when

from src.shared.constant.route_constant import (
    ORDER_BASE,
    ORDER_CANCEL,
    ORDER_MY_ORDERS,
    ORDER_PAY,
)
from tests.shared.utils import create_user, extract_table_data, login_user
from tests.util_constant import (
    ANOTHER_BUYER_EMAIL,
    ANOTHER_BUYER_NAME,
    BUYER1_EMAIL,
    BUYER2_EMAIL,
    BUYER3_EMAIL,
    DEFAULT_PASSWORD,
    SELLER1_EMAIL,
    TEST_CARD_NUMBER,
)


@when('the buyer creates an order for the product')
def buyer_creates_order(client: TestClient, order_state):
    response = client.post(ORDER_BASE, json={'product_id': order_state['product']['id']})
    order_state['response'] = response


@when('the buyer tries to create an order for the product')
def buyer_tries_to_create_order(client: TestClient, order_state):
    response = client.post(ORDER_BASE, json={'product_id': order_state['product']['id']})
    order_state['response'] = response


@when('the seller tries to create an order for their own product')
def seller_tries_to_create_order(client: TestClient, order_state):
    response = client.post(ORDER_BASE, json={'product_id': order_state['product']['id']})
    order_state['response'] = response


@when('the buyer pays for the order with:')
def buyer_pays_for_order(step, client: TestClient, order_state):
    payment_data = extract_table_data(step)
    response = client.post(
        ORDER_PAY.format(order_id=order_state['order']['id']),
        json={'card_number': payment_data['card_number']},
    )
    order_state['response'] = response


@when('the buyer tries to pay for the order again')
def buyer_tries_to_pay_again(client: TestClient, order_state):
    response = client.post(
        ORDER_PAY.format(order_id=order_state['order']['id']),
        json={'card_number': TEST_CARD_NUMBER},
    )
    order_state['response'] = response


@when('the buyer tries to pay for the order')
def buyer_tries_to_pay(client: TestClient, order_state):
    response = client.post(
        ORDER_PAY.format(order_id=order_state['order']['id']),
        json={'card_number': TEST_CARD_NUMBER},
    )
    order_state['response'] = response


@when('another user tries to pay for the order')
def another_user_tries_to_pay(client: TestClient, order_state):
    create_user(client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD, ANOTHER_BUYER_NAME, 'buyer')
    login_user(client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD)
    response = client.post(
        ORDER_PAY.format(order_id=order_state['order']['id']),
        json={'card_number': TEST_CARD_NUMBER},
    )
    order_state['response'] = response


@when('the buyer cancels the order')
def buyer_cancels_order(client: TestClient, order_state):
    response = client.delete(ORDER_CANCEL.format(order_id=order_state['order']['id']))
    order_state['response'] = response


@when('the buyer tries to cancel the order')
def buyer_tries_to_cancel(client: TestClient, order_state):
    response = client.delete(ORDER_CANCEL.format(order_id=order_state['order']['id']))
    order_state['response'] = response


@when("the user tries to cancel someone else's order")
def user_tries_cancel_others_order(client: TestClient, order_state):
    response = client.delete(ORDER_CANCEL.format(order_id=order_state['order']['id']))
    order_state['response'] = response


@when("the seller tries to cancel the buyer's order")
def seller_tries_cancel_buyer_order(client: TestClient, order_state):
    response = client.delete(ORDER_CANCEL.format(order_id=order_state['order']['id']))
    order_state['response'] = response


@when('the buyer tries to cancel a non-existent order')
def buyer_tries_cancel_nonexistent(client: TestClient, order_state):
    # Try to cancel an order that doesn't exist (using ID 999999)
    response = client.delete(ORDER_CANCEL.format(order_id=999999))
    order_state['response'] = response


@when('buyer with id 3 requests their orders')
def buyer_3_requests_orders(client: TestClient, order_state):
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(ORDER_MY_ORDERS)
    order_state['response'] = response


@when('buyer with id 4 requests their orders')
def buyer_4_requests_orders(client: TestClient, order_state):
    login_user(client, BUYER2_EMAIL, DEFAULT_PASSWORD)
    response = client.get(ORDER_MY_ORDERS)
    order_state['response'] = response


@when('buyer with id 5 requests their orders')
def buyer_5_requests_orders(client: TestClient, order_state):
    login_user(client, BUYER3_EMAIL, DEFAULT_PASSWORD)
    response = client.get(ORDER_MY_ORDERS)
    order_state['response'] = response


@when('seller with id 1 requests their orders')
def seller_1_requests_orders(client: TestClient, order_state):
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(ORDER_MY_ORDERS)
    order_state['response'] = response


@when('buyer with id 3 requests their orders with status "paid"')
def buyer_3_requests_orders_paid(client: TestClient, order_state):
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(f'{ORDER_MY_ORDERS}?order_status=paid')
    order_state['response'] = response


@when('buyer with id 3 requests their orders with status "pending_payment"')
def buyer_3_requests_orders_pending(client: TestClient, order_state):
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(f'{ORDER_MY_ORDERS}?order_status=pending_payment')
    order_state['response'] = response
