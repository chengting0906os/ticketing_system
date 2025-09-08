from fastapi.testclient import TestClient
from pytest_bdd import when


@when('I create a product with')
def create_product(step, client: TestClient, product_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    row_data = dict(zip(headers, values, strict=True))
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
    }
    if 'is_active' in row_data:
        request_data['is_active'] = row_data['is_active'].lower() == 'true'
    product_state['request_data'] = request_data
    product_state['response'] = client.post('/api/products', json=product_state['request_data'])


@when('I update the product to')
def update_product(step, client: TestClient, product_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    update_data = dict(zip(headers, values, strict=True))
    if 'price' in update_data:
        update_data['price'] = int(update_data['price'])
    if 'is_active' in update_data:
        update_data['is_active'] = update_data['is_active'].lower() == 'true'
    product_id = product_state['product_id']
    product_state['update_data'] = update_data
    product_state['response'] = client.patch(f'/api/products/{product_id}', json=update_data)


@when('I delete the product')
def delete_product(client: TestClient, product_state):
    product_id = product_state['product_id']
    product_state['response'] = client.delete(f'/api/products/{product_id}')


@when('I try to delete the product')
def try_delete_product(client: TestClient, product_state):
    product_id = product_state['product_id']
    product_state['response'] = client.delete(f'/api/products/{product_id}')


@when('the seller requests their products')
def seller_requests_products(client: TestClient, product_state):
    seller_id = product_state['seller_id']
    product_state['response'] = client.get(f'/api/products?seller_id={seller_id}')


@when('a buyer requests products')
def buyer_requests_products(client: TestClient, product_state):
    product_state['response'] = client.get('/api/products')
