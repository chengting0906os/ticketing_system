from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import PRODUCT_BASE, USER_CREATE
from tests.shared.utils import create_user, extract_table_data, login_user


@given('I am logged in as:')
def login_user_with_table(step, client):
    login_data = extract_table_data(step)
    return login_user(client, login_data['email'], login_data['password'])


@given('a buyer exists:')
def create_buyer_shared(
    step, client: TestClient, order_state=None, product_state=None, user_state=None
):
    """Shared step for creating a buyer user."""
    buyer_data = extract_table_data(step)
    created = create_user(
        client, buyer_data['email'], buyer_data['password'], buyer_data['name'], buyer_data['role']
    )

    buyer = created if created else {'id': 2, 'email': buyer_data['email']}

    # Store in appropriate state based on what's available
    if order_state is not None:
        order_state['buyer'] = buyer
    if product_state is not None:
        product_state['buyer'] = buyer
    if user_state is not None:
        user_state['buyer'] = buyer

    return buyer


@given('a seller exists:')
def create_seller_shared(
    step, client: TestClient, order_state=None, product_state=None, user_state=None
):
    """Shared step for creating a seller user."""
    seller_data = extract_table_data(step)
    created = create_user(
        client,
        seller_data['email'],
        seller_data['password'],
        seller_data['name'],
        seller_data['role'],
    )

    seller = created if created else {'id': 1, 'email': seller_data['email']}

    # Store in appropriate state based on what's available
    if order_state is not None:
        order_state['seller'] = seller
    if product_state is not None:
        product_state['seller'] = seller
    if user_state is not None:
        user_state['seller'] = seller

    return seller


@given('another buyer exists:')
def create_another_buyer_shared(
    step, client: TestClient, order_state=None, product_state=None, user_state=None
):
    """Shared step for creating another buyer user."""
    buyer_data = extract_table_data(step)
    created = create_user(
        client, buyer_data['email'], buyer_data['password'], buyer_data['name'], buyer_data['role']
    )

    another_buyer = created if created else {'id': 3, 'email': buyer_data['email']}

    # Store in appropriate state based on what's available
    if order_state is not None:
        order_state['another_buyer'] = another_buyer
    if product_state is not None:
        product_state['another_buyer'] = another_buyer
    if user_state is not None:
        user_state['another_buyer'] = another_buyer

    return another_buyer


@given('a buyer user exists')
def create_buyer_user_simple(
    step, client: TestClient, user_state=None, order_state=None, product_state=None
):
    """Simple buyer creation without table data."""
    buyer_data = extract_table_data(step)
    response = client.post(USER_CREATE, json=buyer_data)
    assert response.status_code == 201, f'Failed to create buyer user: {response.text}'

    buyer = response.json()

    # Store in appropriate state
    if user_state is not None:
        user_state['buyer'] = buyer
    if order_state is not None:
        order_state['buyer'] = buyer
    if product_state is not None:
        product_state['buyer'] = buyer

    return buyer


@given('a seller user exists')
def create_seller_user_simple(
    step, client: TestClient, product_state=None, order_state=None, user_state=None
):
    """Simple seller creation without table data."""
    user_data = extract_table_data(step)
    created = create_user(
        client, user_data['email'], user_data['password'], user_data['name'], user_data['role']
    )

    if created:
        # Store in appropriate state
        if product_state is not None:
            product_state['seller_id'] = created['id']
            product_state['seller_user'] = created
        if order_state is not None:
            order_state['seller_id'] = created['id']
            order_state['seller_user'] = created
        if user_state is not None:
            user_state['seller_id'] = created['id']
            user_state['seller_user'] = created
    else:
        # User already exists, use default ID
        if product_state is not None:
            product_state['seller_id'] = 1
            product_state['seller_user'] = {'email': user_data['email'], 'role': user_data['role']}
        if order_state is not None:
            order_state['seller_id'] = 1
            order_state['seller_user'] = {'email': user_data['email'], 'role': user_data['role']}
        if user_state is not None:
            user_state['seller_id'] = 1
            user_state['seller_user'] = {'email': user_data['email'], 'role': user_data['role']}

    return created


@given('a seller with a product:')
def create_seller_with_product_shared(
    step, client: TestClient, order_state=None, product_state=None, execute_sql_statement=None
):
    """Shared step for creating a seller with a product."""
    product_data = extract_table_data(step)

    # Create seller
    seller_email = f'seller_{product_data["name"].lower().replace(" ", "_")}@test.com'
    seller = create_user(client, seller_email, 'password123', 'Test Seller', 'seller')

    seller_id = seller['id'] if seller else 1

    # Store seller in appropriate state
    if order_state is not None:
        order_state['seller'] = {'id': seller_id, 'email': seller_email}
    if product_state is not None:
        product_state['seller'] = {'id': seller_id, 'email': seller_email}

    # Login as seller
    login_user(client, seller_email, 'password123')

    # Create product
    request_data = {
        'name': product_data['name'],
        'description': product_data['description'],
        'price': int(product_data['price']),
        'is_active': product_data['is_active'].lower() == 'true',
    }

    response = client.post(PRODUCT_BASE, json=request_data)
    assert response.status_code == 201, f'Failed to create product: {response.text}'
    product = response.json()

    # Update product status if needed
    if 'status' in product_data and product_data['status'] != 'available' and execute_sql_statement:
        execute_sql_statement(
            'UPDATE product SET status = :status WHERE id = :id',
            {'status': product_data['status'], 'id': product['id']},
        )
        product['status'] = product_data['status']

    # Store product in appropriate state
    if order_state is not None:
        order_state['product'] = product
    if product_state is not None:
        product_state['product'] = product
        product_state['product_id'] = product['id']
        product_state['original_product'] = product
        product_state['request_data'] = request_data

    return product


@given('a product exists:')
def create_product_shared(
    step, client: TestClient, order_state=None, product_state=None, execute_sql_statement=None
):
    """Shared step for creating a product (inserts directly into database)."""
    product_data = extract_table_data(step)
    seller_id = int(product_data.get('seller_id', 1))

    if execute_sql_statement:
        # Create product directly in database
        execute_sql_statement(
            """
            INSERT INTO product (name, description, price, seller_id, is_active, status)
            VALUES (:name, :description, :price, :seller_id, :is_active, :status)
            """,
            {
                'name': product_data['name'],
                'description': product_data['description'],
                'price': int(product_data['price']),
                'seller_id': seller_id,
                'is_active': product_data.get('is_active', 'true').lower() == 'true',
                'status': product_data.get('status', 'available'),
            },
        )

        # Get the created product ID
        result = execute_sql_statement(
            'SELECT id FROM product WHERE name = :name ORDER BY id DESC LIMIT 1',
            {'name': product_data['name']},
        )
        product_id = result[0]['id'] if result else 1
    else:
        # Fallback: create via API
        seller_email = f'seller{seller_id}@test.com'
        create_user(client, seller_email, 'password123', f'Test Seller {seller_id}', 'seller')
        login_user(client, seller_email, 'password123')

        request_data = {
            'name': product_data['name'],
            'description': product_data['description'],
            'price': int(product_data['price']),
            'is_active': product_data.get('is_active', 'true').lower() == 'true',
        }

        response = client.post(PRODUCT_BASE, json=request_data)
        assert response.status_code == 201, f'Failed to create product: {response.text}'
        product_result = response.json()
        product_id = product_result['id']

    product = {
        'id': product_id,
        'name': product_data['name'],
        'price': int(product_data['price']),
        'status': product_data.get('status', 'available'),
    }

    # Store product in appropriate state
    if order_state is not None:
        order_state['product'] = product
        order_state['product_id'] = product_id
    if product_state is not None:
        product_state['product'] = product
        product_state['product_id'] = product_id
        product_state['original_product'] = product

    return product
