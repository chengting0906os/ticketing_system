from datetime import datetime
from fastapi.testclient import TestClient
from pytest_bdd import given


@given('a seller with a product:')
def create_seller_with_product(step, client: TestClient, order_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    product_data = dict(zip(headers, values, strict=True))
    seller_response = client.post(
        '/api/users',
        json={
            'email': f'seller_{product_data["name"].lower().replace(" ", "_")}@test.com',
            'password': 'P@ssw0rd',
            'name': 'Test Seller',
            'role': 'seller',
        },
    )
    if seller_response.status_code == 201:
        seller = seller_response.json()
        order_state['seller'] = seller
    else:
        order_state['seller'] = {'id': 1}
    seller_email = f'seller_{product_data["name"].lower().replace(" ", "_")}@test.com'
    login_response = client.post(
        '/api/auth/login',
        data={'username': seller_email, 'password': 'P@ssw0rd'},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    request_data = {
        'name': product_data['name'],
        'description': product_data['description'],
        'price': int(product_data['price']),
        'is_active': product_data['is_active'].lower() == 'true',
    }
    response = client.post('/api/products', json=request_data)
    assert response.status_code == 201, f'Failed to create product: {response.text}'
    product = response.json()
    order_state['product'] = product
    if 'status' in product_data and product_data['status'] != 'available':
        execute_sql_statement(
            'UPDATE product SET status = :status WHERE id = :id',
            {'status': product_data['status'], 'id': product['id']},
        )
        order_state['product']['status'] = product_data['status']


@given('a buyer exists:')
def create_buyer(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    buyer_data = dict(zip(headers, values, strict=True))
    response = client.post(
        '/api/users',
        json={
            'email': buyer_data['email'],
            'password': buyer_data['password'],
            'name': buyer_data['name'],
            'role': buyer_data['role'],
        },
    )
    if response.status_code == 201:
        buyer = response.json()
        order_state['buyer'] = buyer
    else:
        order_state['buyer'] = {'id': 2, 'email': buyer_data['email']}


@given('an order exists with status "pending_payment":')
def create_pending_order(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    order_data = dict(zip(headers, values, strict=True))
    seller_response = client.post(
        '/api/users',
        json={
            'email': 'seller@test.com',
            'password': 'P@ssw0rd',
            'name': 'Test Seller',
            'role': 'seller',
        },
    )
    if seller_response.status_code == 201:
        seller = seller_response.json()
        seller_id = seller['id']
    else:
        seller_id = int(order_data['seller_id'])
    buyer_response = client.post(
        '/api/users',
        json={
            'email': 'buyer@test.com',
            'password': 'P@ssw0rd',
            'name': 'Test Buyer',
            'role': 'buyer',
        },
    )
    if buyer_response.status_code == 201:
        buyer = buyer_response.json()
        buyer_id = buyer['id']
    else:
        buyer_id = int(order_data['buyer_id'])
    login_response = client.post(
        '/api/auth/login',
        data={'username': 'seller@test.com', 'password': 'P@ssw0rd'},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Seller login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    product_response = client.post(
        '/api/products',
        json={
            'name': 'Test Product',
            'description': 'Test Description',
            'price': int(order_data['price']),
            'is_active': True,
        },
    )
    assert product_response.status_code == 201, f'Failed to create product: {product_response.text}'
    product = product_response.json()
    login_response = client.post(
        '/api/auth/login',
        data={'username': 'buyer@test.com', 'password': 'P@ssw0rd'},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Buyer login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    order_response = client.post('/api/orders', json={'product_id': product['id']})
    assert order_response.status_code == 201, f'Failed to create order: {order_response.text}'
    order = order_response.json()
    order_state['order'] = order
    order_state['buyer_id'] = buyer_id
    order_state['seller_id'] = seller_id
    order_state['product_id'] = product['id']


@given('an order exists with status "paid":')
def create_paid_order(step, client: TestClient, order_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    order_data = dict(zip(headers, values, strict=True))
    create_pending_order(step, client, order_state)
    if 'paid_at' in order_data and order_data['paid_at'] == 'not_null':
        execute_sql_statement(
            'UPDATE "order" SET status = \'paid\', paid_at = :paid_at WHERE id = :id',
            {'paid_at': datetime.now(), 'id': order_state['order']['id']},
        )
        order_state['order']['status'] = 'paid'
        order_state['order']['paid_at'] = datetime.now().isoformat()


@given('an order exists with status "cancelled":')
def create_cancelled_order(step, client: TestClient, order_state, execute_sql_statement):
    create_pending_order(step, client, order_state)
    execute_sql_statement(
        'UPDATE "order" SET status = \'cancelled\' WHERE id = :id',
        {'id': order_state['order']['id']},
    )
    execute_sql_statement(
        "UPDATE product SET status = 'available' WHERE id = :id", {'id': order_state['product_id']}
    )
    order_state['order']['status'] = 'cancelled'


@given('users exist:')
def create_users(step, client: TestClient, order_state, execute_sql_statement):
    import bcrypt

    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    order_state['users'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        user_data = dict(zip(headers, values, strict=True))
        user_id = int(user_data['id'])
        hashed_password = bcrypt.hashpw(
            user_data['password'].encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        execute_sql_statement(
            '\n                INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)\n                VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)\n            ',
            {
                'id': user_id,
                'email': user_data['email'],
                'hashed_password': hashed_password,
                'name': user_data['name'],
                'role': user_data['role'],
            },
        )
        order_state['users'][user_id] = {
            'id': user_id,
            'email': user_data['email'],
            'name': user_data['name'],
            'role': user_data['role'],
        }
    execute_sql_statement(
        'SELECT setval(\'user_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "user"), false)', {}
    )


@given('products exist:')
def create_products(step, client: TestClient, order_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    order_state['products'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        product_data = dict(zip(headers, values, strict=True))
        product_id = int(product_data['id'])
        seller_id = int(product_data['seller_id'])
        execute_sql_statement(
            '\n                INSERT INTO product (id, seller_id, name, description, price, is_active, status)\n                VALUES (:id, :seller_id, :name, :description, :price, :is_active, :status)\n            ',
            {
                'id': product_id,
                'seller_id': seller_id,
                'name': product_data['name'],
                'description': f'Description for {product_data["name"]}',
                'price': int(product_data['price']),
                'is_active': True,
                'status': product_data['status'],
            },
        )
        order_state['products'][product_id] = {
            'id': product_id,
            'seller_id': seller_id,
            'name': product_data['name'],
            'price': int(product_data['price']),
            'status': product_data['status'],
        }
    execute_sql_statement(
        "SELECT setval('product_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM product), false)", {}
    )


@given('orders exist:')
def create_orders(step, client: TestClient, order_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    order_state['orders'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        order_data = dict(zip(headers, values, strict=True))
        product_key = int(order_data['product_id'])
        if 'products' in order_state and product_key in order_state['products']:
            product_id = order_state['products'][product_key]['id']
        else:
            product_id = product_key
        order_id = int(order_data['id'])
        if order_data.get('paid_at') == 'not_null' and order_data['status'] == 'paid':
            execute_sql_statement(
                '\n                    INSERT INTO "order" (id, buyer_id, seller_id, product_id, price, status, created_at, updated_at, paid_at)\n                    VALUES (:id, :buyer_id, :seller_id, :product_id, :price, :status, NOW(), NOW(), NOW())\n                ',
                {
                    'id': order_id,
                    'buyer_id': int(order_data['buyer_id']),
                    'seller_id': int(order_data['seller_id']),
                    'product_id': product_id,
                    'price': int(order_data['price']),
                    'status': order_data['status'],
                },
            )
        else:
            execute_sql_statement(
                '\n                    INSERT INTO "order" (id, buyer_id, seller_id, product_id, price, status, created_at, updated_at)\n                    VALUES (:id, :buyer_id, :seller_id, :product_id, :price, :status, NOW(), NOW())\n                ',
                {
                    'id': order_id,
                    'buyer_id': int(order_data['buyer_id']),
                    'seller_id': int(order_data['seller_id']),
                    'product_id': product_id,
                    'price': int(order_data['price']),
                    'status': order_data['status'],
                },
            )
        order_state['orders'][int(order_data['id'])] = {'id': order_id}
    execute_sql_statement(
        'SELECT setval(\'order_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "order"), false)', {}
    )
