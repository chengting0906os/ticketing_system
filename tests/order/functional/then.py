from typing import Any, Dict, List

from fastapi.testclient import TestClient
from pytest_bdd import then

from src.shared.constant.route_constant import ORDER_GET, PRODUCT_GET
from tests.shared.utils import extract_single_value, extract_table_data


def assert_nullable_field(
    data: Dict[str, Any], field: str, expected: str, message: str | None = None
):
    if expected == 'not_null':
        assert data.get(field) is not None, message or f'{field} should not be null'
    elif expected == 'null':
        assert data.get(field) is None, message or f'{field} should be null'


def assert_response_status(response, expected_status: int, message: str | None = None):
    assert response.status_code == expected_status, (
        message or f'Expected {expected_status}, got {response.status_code}: {response.text}'
    )


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


@then('the product status should be "reserved"')
def verify_product_status_reserved(client: TestClient, order_state):
    product_id = order_state['product']['id']
    status = get_product_status(client, product_id)
    assert status == 'reserved'


@then('the order status should be "paid"')
def verify_order_status_paid(client: TestClient, order_state):
    order_data = get_order_details(client, order_state['order']['id'])
    assert order_data['status'] == 'paid'
    order_state['updated_order'] = order_data


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


@then('the order status should be:')
def verify_order_status(step, client: TestClient, order_state):
    expected_status = extract_single_value(step)
    order_data = get_order_details(client, order_state['order']['id'])
    assert order_data['status'] == expected_status
    order_state['updated_order'] = order_data


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
