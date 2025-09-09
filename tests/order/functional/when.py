from fastapi.testclient import TestClient
from pytest_bdd import when

from src.shared.constant.route_constant import (
    ORDER_BASE,
    ORDER_CANCEL,
    ORDER_GET,
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
    # The buyer should already be logged in via "I am logged in as:" step
    # If not, we don't login here - let the test control authentication

    response = client.post(ORDER_BASE, json={'product_id': order_state['product']['id']})
    order_state['response'] = response

    # Store order if created successfully
    if response.status_code == 201:
        order_state['order'] = response.json()


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
    order_id = order_state['order']['id']
    response = client.post(
        ORDER_PAY.format(order_id=order_id),
        json={'card_number': payment_data['card_number']},
    )
    order_state['response'] = response

    # If payment was successful, fetch the updated order details
    if response.status_code == 200:
        order_response = client.get(ORDER_GET.format(order_id=order_id))
        assert order_response.status_code == 200
        order_state['updated_order'] = order_response.json()  # Store full order details


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
    order_id = order_state['order']['id']
    response = client.delete(ORDER_CANCEL.format(order_id=order_id))
    order_state['response'] = response
    if response.status_code == 204:
        # Fetch the updated order details after cancellation
        order_response = client.get(ORDER_GET.format(order_id=order_id))
        assert order_response.status_code == 200
        updated_order = order_response.json()
        order_state['order']['status'] = 'cancelled'
        order_state['updated_order'] = updated_order  # Store full order details


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


@when('the buyer tries to create an order for the negative price product')
def buyer_tries_to_create_order_for_negative_price_product(client: TestClient, order_state):
    """Try to create an order for a product with negative price."""
    # Login as buyer
    buyer = order_state['buyer']
    login_user(client, buyer['email'], 'P@ssw0rd')

    # Try to create order
    response = client.post(ORDER_BASE, json={'product_id': order_state['product_id']})
    order_state['response'] = response


@when('the buyer tries to create an order for the zero price product')
def buyer_tries_to_create_order_for_zero_price_product(client: TestClient, order_state):
    """Try to create an order for a product with zero price."""
    # Login as buyer
    buyer = order_state['buyer']
    login_user(client, buyer['email'], 'P@ssw0rd')

    # Try to create order
    response = client.post(ORDER_BASE, json={'product_id': order_state['product_id']})
    order_state['response'] = response


@when('the product price is updated to 2000')
def update_product_price_to_2000(client: TestClient, order_state, execute_sql_statement):
    """Update the product price in the database."""
    product_id = order_state['product']['id']

    # Update product price directly in database
    execute_sql_statement(
        'UPDATE product SET price = :price WHERE id = :id',
        {'price': 2000, 'id': product_id},
    )
    order_state['product']['price'] = 2000


@when('the product price is updated to 3000')
def update_product_price_to_3000(client: TestClient, order_state, execute_sql_statement):
    """Update the product price in the database."""
    product_id = order_state['product']['id']

    # Update product price directly in database
    execute_sql_statement(
        'UPDATE product SET price = :price WHERE id = :id',
        {'price': 3000, 'id': product_id},
    )
    order_state['product']['price'] = 3000


@when('the buyer pays for the order')
def buyer_pays_for_order_simple(client: TestClient, order_state):
    """Buyer pays for their order."""
    # Login as buyer
    buyer = order_state['buyer']
    login_user(client, buyer['email'], 'P@ssw0rd')

    # Pay for the order
    order_id = order_state['order']['id']
    response = client.post(
        ORDER_PAY.format(order_id=order_id),
        json={'card_number': TEST_CARD_NUMBER},
    )
    assert response.status_code == 200, f'Failed to pay for order: {response.text}'
    order_state['payment_response'] = response
    order_state['response'] = response  # Set response for Then steps

    # Fetch the updated order details after payment
    order_response = client.get(ORDER_GET.format(order_id=order_id))
    assert order_response.status_code == 200
    order_state['updated_order'] = order_response.json()  # Store full order details


@when('the buyer cancels the order to release the product')
def buyer_cancels_order_to_release_product(client: TestClient, order_state):
    """Buyer cancels their order to release the product."""
    # Login as buyer
    buyer = order_state['buyer']
    login_user(client, buyer['email'], 'P@ssw0rd')

    # Cancel the order
    order_id = order_state['order']['id']
    response = client.delete(ORDER_CANCEL.format(order_id=order_id))
    assert response.status_code == 204, f'Failed to cancel order: {response.text}'
    order_state['order']['status'] = 'cancelled'


@when('another buyer creates an order for the same product')
def another_buyer_creates_order_for_same_product(client: TestClient, order_state):
    """Another buyer creates an order for the same product."""
    # Create another buyer
    another_buyer_email = 'another_buyer@test.com'
    another_buyer = create_user(client, another_buyer_email, 'P@ssw0rd', 'Another Buyer', 'buyer')

    if not another_buyer:
        # User already exists, just use it
        another_buyer = {'email': another_buyer_email}

    # Login as the other buyer
    login_user(client, another_buyer_email, 'P@ssw0rd')

    # Create order for the same product
    response = client.post(ORDER_BASE, json={'product_id': order_state['product']['id']})
    assert response.status_code == 201, f'Failed to create new order: {response.text}'

    order_state['new_order'] = response.json()
    order_state['another_buyer'] = another_buyer


@when('the buyer tries to change cancelled order status to pending_payment')
def buyer_tries_change_cancelled_to_pending(client: TestClient, order_state):
    """Buyer tries to change cancelled order back to pending_payment."""
    order_id = order_state['order']['id']
    # Try to update order status (this endpoint may not exist, but we'll simulate the attempt)
    response = client.patch(
        f'{ORDER_BASE}/{order_id}/status',
        json={'status': 'pending_payment'},
    )
    order_state['response'] = response


@when('the buyer tries to change paid order status to pending_payment')
def buyer_tries_change_paid_to_pending(client: TestClient, order_state):
    """Buyer tries to change paid order back to pending_payment."""
    order_id = order_state['order']['id']
    # Try to update order status
    response = client.patch(
        f'{ORDER_BASE}/{order_id}/status',
        json={'status': 'pending_payment'},
    )
    order_state['response'] = response


@when('the buyer tries to cancel the completed order')
def buyer_tries_cancel_completed_order(client: TestClient, order_state):
    """Buyer tries to cancel a completed order."""
    order_id = order_state['order']['id']
    response = client.delete(ORDER_CANCEL.format(order_id=order_id))
    order_state['response'] = response


@when('the buyer tries to mark unpaid order as completed')
def buyer_tries_mark_unpaid_as_completed(client: TestClient, order_state):
    """Buyer tries to mark an unpaid order as completed."""
    order_id = order_state['order']['id']
    # Try to complete order without payment
    response = client.patch(
        f'{ORDER_BASE}/{order_id}/complete',
        json={},
    )
    order_state['response'] = response


@when('the seller marks the order as completed')
def seller_marks_order_completed(client: TestClient, order_state):
    """Seller marks the order as completed."""
    # First, login as seller
    login_user(client, 'seller@test.com', 'P@ssw0rd')

    order_id = order_state['order']['id']
    response = client.patch(
        f'{ORDER_BASE}/{order_id}/complete',
        json={},
    )
    order_state['response'] = response
    if response.status_code == 200:
        order_state['order']['status'] = 'completed'
