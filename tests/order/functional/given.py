"""Given steps for order BDD tests."""

import asyncio

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
