"""Given steps for order BDD tests."""

import asyncio
from datetime import datetime

from fastapi.testclient import TestClient
from pytest_bdd import given
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@given('a seller with a product:')
def create_seller_with_product(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    product_data = dict(zip(headers, values, strict=True))
    
    # First create a seller user
    seller_response = client.post('/api/users', json={
        'email': f'seller_{product_data["name"].lower().replace(" ", "_")}@test.com',
        'password': 'password123',
        'name': 'Test Seller',
        'role': 'seller',
    })
    
    if seller_response.status_code == 201:
        seller = seller_response.json()
        order_state['seller'] = seller
    else:
        # If user exists, try to find one
        order_state['seller'] = {'id': 1}
    
    # Create the product
    request_data = {
        'name': product_data['name'],
        'description': product_data['description'],
        'price': int(product_data['price']),
        'seller_id': order_state['seller']['id'],
        'is_active': product_data['is_active'].lower() == 'true'
    }
    
    response = client.post('/api/products', json=request_data)
    assert response.status_code == 201, f"Failed to create product: {response.text}"
    
    product = response.json()
    order_state['product'] = product
    
    # If status is not 'available', need to update it directly in database
    if 'status' in product_data and product_data['status'] != 'available':
        async def update_product_status():
            TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE products SET status = :status WHERE id = :id"),
                    {"status": product_data['status'], "id": product['id']}
                )
            await engine.dispose()
        
        asyncio.run(update_product_status())
        order_state['product']['status'] = product_data['status']


@given('a buyer exists:')
def create_buyer(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    buyer_data = dict(zip(headers, values, strict=True))
    
    # Create the buyer user
    response = client.post('/api/users', json={
        'email': buyer_data['email'],
        'password': buyer_data['password'],
        'name': buyer_data['name'],
        'role': buyer_data['role'],
    })
    
    if response.status_code == 201:
        buyer = response.json()
        order_state['buyer'] = buyer
    else:
        # If user exists, we can still use it
        order_state['buyer'] = {'id': 2, 'email': buyer_data['email']}


@given('an order exists with status "pending_payment":')
def create_pending_order(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    order_data = dict(zip(headers, values, strict=True))
    
    # First create users and product
    # Create seller
    seller_response = client.post('/api/users', json={
        'email': 'seller@test.com',
        'password': 'password123',
        'name': 'Test Seller',
        'role': 'seller',
    })
    if seller_response.status_code == 201:
        seller = seller_response.json()
        seller_id = seller['id']
    else:
        seller_id = int(order_data['seller_id'])
    
    # Create buyer
    buyer_response = client.post('/api/users', json={
        'email': 'buyer@test.com',
        'password': 'password123',
        'name': 'Test Buyer',
        'role': 'buyer',
    })
    if buyer_response.status_code == 201:
        buyer = buyer_response.json()
        buyer_id = buyer['id']
    else:
        buyer_id = int(order_data['buyer_id'])
    
    # Create product
    product_response = client.post('/api/products', json={
        'name': 'Test Product',
        'description': 'Test Description',
        'price': int(order_data['price']),
        'seller_id': seller_id,
        'is_active': True
    })
    assert product_response.status_code == 201, f"Failed to create product: {product_response.text}"
    product = product_response.json()
    
    # Create order
    order_response = client.post('/api/orders', json={
        'buyer_id': buyer_id,
        'product_id': product['id']
    })
    assert order_response.status_code == 201, f"Failed to create order: {order_response.text}"
    order = order_response.json()
    
    order_state['order'] = order
    order_state['buyer_id'] = buyer_id
    order_state['seller_id'] = seller_id
    order_state['product_id'] = product['id']


@given('an order exists with status "paid":')
def create_paid_order(step, client: TestClient, order_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    order_data = dict(zip(headers, values, strict=True))
    
    # First create a pending order
    create_pending_order(step, client, order_state)
    
    # Update order status to paid in database
    if 'paid_at' in order_data and order_data['paid_at'] == 'not_null':
        async def update_order_to_paid():
            TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE orders SET status = 'paid', paid_at = :paid_at WHERE id = :id"),
                    {"paid_at": datetime.now(), "id": order_state['order']['id']}
                )
            await engine.dispose()
        
        asyncio.run(update_order_to_paid())
        order_state['order']['status'] = 'paid'
        order_state['order']['paid_at'] = datetime.now().isoformat()


@given('an order exists with status "cancelled":')
def create_cancelled_order(step, client: TestClient, order_state):
    create_pending_order(step, client, order_state)
    
    # Update order status to cancelled in database
    async def update_order_to_cancelled():
        TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE orders SET status = 'cancelled' WHERE id = :id"),
                {"id": order_state['order']['id']}
            )
            # Also update product back to available
            await conn.execute(
                text("UPDATE products SET status = 'available' WHERE id = :id"),
                {"id": order_state['product_id']}
            )
        await engine.dispose()
    
    asyncio.run(update_order_to_cancelled())
    order_state['order']['status'] = 'cancelled'


@given('users exist:')
def create_users(step, client: TestClient, order_state):
    """Create multiple users from table data."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    
    order_state['users'] = {}
    
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        user_data = dict(zip(headers, values, strict=True))
        
        # Try to create user
        response = client.post('/api/users', json={
            'email': user_data['email'],
            'password': user_data['password'],
            'name': user_data['name'],
            'role': user_data['role'],
        })
        
        if response.status_code == 201:
            user = response.json()
            order_state['users'][int(user_data['id'])] = user
        else:
            # Store with the ID from table
            order_state['users'][int(user_data['id'])] = {
                'id': int(user_data['id']),
                'email': user_data['email'],
                'name': user_data['name'],
                'role': user_data['role']
            }


@given('products exist:')
def create_products(step, client: TestClient, order_state):
    """Create multiple products from table data."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    
    order_state['products'] = {}
    
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        product_data = dict(zip(headers, values, strict=True))
        
        response = client.post('/api/products', json={
            'name': product_data['name'],
            'description': f"Description for {product_data['name']}",
            'price': int(product_data['price']),
            'seller_id': int(product_data['seller_id']),
            'is_active': True
        })
        
        if response.status_code == 201:
            product = response.json()
            order_state['products'][int(product_data['id'])] = product
            
            # Update product status if needed
            if product_data['status'] != 'available':
                async def update_product_status(product_id, status):
                    TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
                    engine = create_async_engine(TEST_DATABASE_URL)
                    async with engine.begin() as conn:
                        await conn.execute(
                            text("UPDATE products SET status = :status WHERE id = :id"),
                            {"status": product_data['status'], "id": product['id']}
                        )
                    await engine.dispose()
                
                asyncio.run(update_product_status(product['id'], product_data['status']))


@given('orders exist:')  
def create_orders(step, client: TestClient, order_state):
    """Create multiple orders from table data."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    
    order_state['orders'] = {}
    
    # Directly insert orders into database for testing
    async def insert_orders():
        TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            for row in rows[1:]:
                values = [cell.value for cell in row.cells]
                order_data = dict(zip(headers, values, strict=True))
                
                # Get actual product ID from state
                product_id = order_state['products'][int(order_data['product_id'])]['id']
                
                # Insert order directly
                if order_data.get('paid_at') == 'not_null' and order_data['status'] == 'paid':
                    result = await conn.execute(
                        text("""
                            INSERT INTO orders (buyer_id, seller_id, product_id, price, status, created_at, updated_at, paid_at)
                            VALUES (:buyer_id, :seller_id, :product_id, :price, :status, NOW(), NOW(), NOW())
                            RETURNING id
                        """),
                        {
                            "buyer_id": int(order_data['buyer_id']),
                            "seller_id": int(order_data['seller_id']),
                            "product_id": product_id,
                            "price": int(order_data['price']),
                            "status": order_data['status']
                        }
                    )
                else:
                    result = await conn.execute(
                        text("""
                            INSERT INTO orders (buyer_id, seller_id, product_id, price, status, created_at, updated_at)
                            VALUES (:buyer_id, :seller_id, :product_id, :price, :status, NOW(), NOW())
                            RETURNING id
                        """),
                        {
                            "buyer_id": int(order_data['buyer_id']),
                            "seller_id": int(order_data['seller_id']),
                            "product_id": product_id,
                            "price": int(order_data['price']),
                            "status": order_data['status']
                        }
                    )
                
                order_id = result.scalar()
                order_state['orders'][int(order_data['id'])] = {'id': order_id}
        
        await engine.dispose()
    
    asyncio.run(insert_orders())
