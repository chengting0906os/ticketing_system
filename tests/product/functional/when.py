from fastapi.testclient import TestClient
from pytest_bdd import when

from tests.route_constant import (
    PRODUCT_BASE,
    PRODUCT_DELETE,
    PRODUCT_LIST,
    PRODUCT_UPDATE,
)
from tests.shared.utils import extract_table_data


@when('I create a product with')
def create_product(step, client: TestClient, product_state):
    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
    }
    if 'is_active' in row_data:
        request_data['is_active'] = row_data['is_active'].lower() == 'true'
    product_state['request_data'] = request_data
    product_state['response'] = client.post(PRODUCT_BASE, json=product_state['request_data'])


@when('I update the product to')
def update_product(step, client: TestClient, product_state):
    update_data = extract_table_data(step)
    if 'price' in update_data:
        update_data['price'] = int(update_data['price'])
    if 'is_active' in update_data:
        update_data['is_active'] = update_data['is_active'].lower() == 'true'
    product_id = product_state['product_id']
    product_state['update_data'] = update_data
    product_state['response'] = client.patch(
        PRODUCT_UPDATE.format(product_id=product_id), json=update_data
    )


@when('I delete the product')
def delete_product(client: TestClient, product_state):
    product_id = product_state['product_id']
    product_state['response'] = client.delete(PRODUCT_DELETE.format(product_id=product_id))


@when('I try to delete the product')
def try_delete_product(client: TestClient, product_state):
    product_id = product_state['product_id']
    product_state['response'] = client.delete(PRODUCT_DELETE.format(product_id=product_id))


@when('the seller requests their products')
def seller_requests_products(client: TestClient, product_state):
    seller_id = product_state['seller_id']
    product_state['response'] = client.get(f'{PRODUCT_LIST}?seller_id={seller_id}')


@when('a buyer requests products')
def buyer_requests_products(client: TestClient, product_state):
    product_state['response'] = client.get(PRODUCT_BASE)
