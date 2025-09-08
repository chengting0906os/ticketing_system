from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import PRODUCT_BASE
from tests.shared.utils import create_user, extract_table_data, login_user
from tests.util_constant import (
    DEFAULT_PASSWORD,
    EMPTY_LIST_SELLER_EMAIL,
    EMPTY_LIST_SELLER_NAME,
    LIST_SELLER_EMAIL,
    LIST_TEST_SELLER_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


@given('a product exists')
def product_exists(step, client: TestClient, product_state):
    row_data = extract_table_data(step)
    seller_email = TEST_SELLER_EMAIL
    create_user(client, seller_email, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
    login_user(client, seller_email, DEFAULT_PASSWORD)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'is_active': row_data['is_active'].lower() == 'true',
    }
    response = client.post(PRODUCT_BASE, json=request_data)
    assert response.status_code == 201, f'Failed to create product: {response.text}'
    product_data = response.json()
    product_state['product_id'] = product_data['id']
    product_state['original_product'] = product_data
    product_state['request_data'] = request_data


@given('a product exists with:')
def product_exists_with_status(step, client: TestClient, product_state, execute_sql_statement):
    row_data = extract_table_data(step)
    seller_id = int(row_data['seller_id'])
    seller_email = f'seller{seller_id}@test.com'
    created_user = create_user(
        client, seller_email, DEFAULT_PASSWORD, f'Test Seller {seller_id}', 'seller'
    )
    if created_user:
        seller_id = created_user['id']
    login_user(client, seller_email, DEFAULT_PASSWORD)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'is_active': row_data['is_active'].lower() == 'true',
    }
    response = client.post(PRODUCT_BASE, json=request_data)
    assert response.status_code == 201, f'Failed to create product: {response.text}'
    product_data = response.json()
    product_state['product_id'] = product_data['id']
    if 'status' in row_data and row_data['status'] != 'available':
        execute_sql_statement(
            'UPDATE product SET status = :status WHERE id = :id',
            {'status': row_data['status'], 'id': product_data['id']},
        )
        product_data['status'] = row_data['status']
    product_state['original_product'] = product_data
    product_state['request_data'] = request_data


@given('a seller with products:')
def create_seller_with_products(step, client: TestClient, product_state, execute_sql_statement):
    created_user = create_user(
        client, LIST_SELLER_EMAIL, DEFAULT_PASSWORD, LIST_TEST_SELLER_NAME, 'seller'
    )
    seller_id = created_user['id'] if created_user else 1
    product_state['seller_id'] = seller_id
    product_state['created_products'] = []
    login_user(client, LIST_SELLER_EMAIL, DEFAULT_PASSWORD)
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        product_data = dict(zip(headers, values, strict=True))
        create_response = client.post(
            PRODUCT_BASE,
            json={
                'name': product_data['name'],
                'description': product_data['description'],
                'price': int(product_data['price']),
                'is_active': product_data['is_active'].lower() == 'true',
            },
        )
        if create_response.status_code == 201:
            created_product = create_response.json()
            product_id = created_product['id']
            if product_data['status'] != 'available':
                execute_sql_statement(
                    'UPDATE product SET status = :status WHERE id = :id',
                    {'status': product_data['status'], 'id': product_id},
                )
                created_product['status'] = product_data['status']
            product_state['created_products'].append(created_product)


@given('no available products exist')
def create_no_available_products(step, client: TestClient, product_state, execute_sql_statement):
    created_user = create_user(
        client, EMPTY_LIST_SELLER_EMAIL, DEFAULT_PASSWORD, EMPTY_LIST_SELLER_NAME, 'seller'
    )
    seller_id = created_user['id'] if created_user else 1
    product_state['seller_id'] = seller_id
    product_state['created_products'] = []
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        product_data = dict(zip(headers, values, strict=True))
        create_response = client.post(
            PRODUCT_BASE,
            json={
                'name': product_data['name'],
                'description': product_data['description'],
                'price': int(product_data['price']),
                'seller_id': seller_id,
                'is_active': product_data['is_active'].lower() == 'true',
            },
        )
        if create_response.status_code == 201:
            created_product = create_response.json()
            product_id = created_product['id']
            execute_sql_statement(
                'UPDATE product SET status = :status WHERE id = :id',
                {'status': product_data['status'], 'id': product_id},
            )
            created_product['status'] = product_data['status']
            product_state['created_products'].append(created_product)
