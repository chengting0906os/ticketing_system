from typing import Any, Dict, List

from fastapi.testclient import TestClient
from pytest_bdd import then

from src.shared.constant.route_constant import ORDER_GET, PRODUCT_GET
from tests.shared.utils import extract_single_value, extract_table_data, assert_response_status


def assert_nullable_field(
    data: Dict[str, Any], field: str, expected: str, message: str | None = None
):
    if expected == 'not_null':
        assert data.get(field) is not None, message or f'{field} should not be null'
    elif expected == 'null':
        assert data.get(field) is None, message or f'{field} should be null'


def get_product_status(client: TestClient, product_id: int) -> str:
    response = client.get(PRODUCT_GET.format(product_id=product_id))
    assert_response_status(response, 200)
    return response.json()['status']


def get_order_details(client: TestClient, order_id: int) -> Dict[str, Any]:
    response = client.get(ORDER_GET.format(order_id=order_id))
    assert_response_status(response, 200)
    return response.json()


def assert_order_count(order_state: Dict[str, Any], expected_count: int):
    response = order_state['response']
    assert_response_status(response, 200)
    orders = response.json()
    assert len(orders) == expected_count, f'Expected {expected_count} orders, got {len(orders)}'
    order_state['orders_response'] = orders


def verify_order_fields(order_data: Dict[str, Any], expected_data: Dict[str, str]):
    if 'price' in expected_data:
        assert order_data['price'] == int(expected_data['price'])
    if 'status' in expected_data:
        assert order_data['status'] == expected_data['status']
    if 'created_at' in expected_data:
        assert_nullable_field(order_data, 'created_at', expected_data['created_at'])
    if 'paid_at' in expected_data:
        assert_nullable_field(order_data, 'paid_at', expected_data['paid_at'])


def assert_all_orders_have_status(orders: List[Dict[str, Any]], expected_status: str):
    for order in orders:
        assert order.get('status') == expected_status, (
            f'Order {order["id"]} has status {order.get("status")}, expected {expected_status}'
        )


@then('the order should be created with:')
def verify_order_created(step, order_state):
    expected_data = extract_table_data(step)
    response = order_state['response']
    assert_response_status(response, 201)
    order_data = response.json()
    verify_order_fields(order_data, expected_data)
    order_state['created_order'] = order_data


@then('the order status should remain:')
def verify_order_status_remains(step, client: TestClient, order_state):
    expected_status = extract_single_value(step)
    order_data = get_order_details(client, order_state['order']['id'])
    assert order_data['status'] == expected_status, (
        f'Order status should remain {expected_status}, but got {order_data["status"]}'
    )


@then('the product status should remain:')
def verify_product_status_remains(step, client: TestClient, order_state):
    expected_status = extract_single_value(step)
    product_id = order_state.get('product', {}).get('id') or order_state.get('product_id', 1)
    actual_status = get_product_status(client, product_id)
    assert actual_status == expected_status, (
        f'Product status should remain {expected_status}, but got {actual_status}'
    )


@then('the order should have:')
def verify_order_has_fields(step, order_state):
    expected_data = extract_table_data(step)
    order_data = order_state.get('updated_order') or order_state['response'].json()
    for field in ['created_at', 'paid_at']:
        if field in expected_data:
            assert_nullable_field(order_data, field, expected_data[field])


@then('the payment should have:')
def verify_payment_details(step, order_state):
    expected_data = extract_table_data(step)
    response_data = order_state['response'].json()
    if 'payment_id' in expected_data:
        if expected_data['payment_id'].startswith('PAY_MOCK_'):
            assert response_data.get('payment_id', '').startswith('PAY_MOCK_'), (
                'payment_id should start with PAY_MOCK_'
            )
    if 'status' in expected_data:
        assert response_data.get('status') == expected_data['status'], (
            f'payment status should be {expected_data["status"]}'
        )


@then('the product status should be:')
def verify_product_status(step, client: TestClient, order_state):
    expected_status = extract_single_value(step)
    product_id = order_state.get('product_id') or order_state['product']['id']
    status = get_product_status(client, product_id)
    assert status == expected_status


@then('the response should contain orders:')
def verify_orders_count_with_table(step, order_state):
    expected_count = int(extract_single_value(step))
    assert_order_count(order_state, expected_count)


@then('the orders should include:')
def verify_orders_details(step, order_state):
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    orders = order_state['orders_response']
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_data = dict(zip(headers, values, strict=True))
        order_id = int(expected_data['id'])
        order = next((o for o in orders if o['id'] == order_id), None)
        assert order is not None, f'Order with id {order_id} not found in response'
        field_mappings = {
            'product_name': ('product_name', str),
            'price': ('price', int),
            'status': ('status', str),
            'seller_name': ('seller_name', str),
            'buyer_name': ('buyer_name', str),
        }
        for expected_field, (actual_field, converter) in field_mappings.items():
            if expected_field in expected_data:
                expected_value = expected_data[expected_field]
                if converter is int:
                    expected_value = converter(expected_value)
                assert order.get(actual_field) == expected_value
        for field in ['created_at', 'paid_at']:
            if field in expected_data:
                assert_nullable_field(order, field, expected_data[field])


@then('all orders should have status:')
def verify_all_orders_status(step, order_state):
    expected_status = extract_single_value(step)
    assert_all_orders_have_status(order_state['orders_response'], expected_status)


@then('the error message should contain "Price must be positive"')
def verify_price_error_message(order_state):
    """Verify error message contains price validation error."""
    response = order_state['response']
    assert response.status_code == 400, f'Expected status 400, got {response.status_code}'
    error_data = response.json()

    # Check if error message contains the expected text
    error_message = str(error_data.get('detail', ''))
    assert 'Price must be positive' in error_message, (
        f'Expected "Price must be positive" in error message, got: {error_message}'
    )


@then('the order price should be 1000')
def verify_order_price_1000(order_state):
    """Verify the order price is 1000."""
    order = order_state['order']
    assert order['price'] == 1000, f'Expected order price 1000, got {order["price"]}'


@then('the existing order price should remain 1000')
def verify_existing_order_price_remains_1000(client: TestClient, order_state):
    """Verify the existing order price remains 1000 after product price change."""
    order_id = order_state['order']['id']
    order_data = get_order_details(client, order_id)
    assert order_data['price'] == 1000, (
        f'Expected order price to remain 1000, got {order_data["price"]}'
    )


@then('the new order should have price 2000')
def verify_new_order_has_price_2000(order_state):
    """Verify the new order has the updated price of 2000."""
    new_order = order_state['new_order']
    assert new_order['price'] == 2000, f'Expected new order price 2000, got {new_order["price"]}'


@then('the paid order price should remain 1500')
def verify_paid_order_price_remains_1500(client: TestClient, order_state):
    """Verify the paid order price remains 1500 after product price change."""
    order_id = order_state['order']['id']
    order_data = get_order_details(client, order_id)
    assert order_data['price'] == 1500, (
        f'Expected paid order price to remain 1500, got {order_data["price"]}'
    )


@then('the order status should remain "paid"')
def verify_order_status_remains_paid(client: TestClient, order_state):
    """Verify the order status remains paid."""
    order_id = order_state['order']['id']
    order_data = get_order_details(client, order_id)
    assert order_data['status'] == 'paid', (
        f'Expected order status to remain "paid", got {order_data["status"]}'
    )


@then('the product status should be "reserved"')
def verify_product_status_is_reserved(client: TestClient, order_state):
    """Verify the product status is reserved."""
    product_id = order_state['product']['id']
    response = client.get(PRODUCT_GET.format(product_id=product_id))
    assert response.status_code == 200, f'Failed to get product: {response.text}'
    product_data = response.json()
    assert product_data['status'] == 'reserved', (
        f'Expected product status "reserved", got {product_data["status"]}'
    )
