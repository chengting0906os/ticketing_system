"""Given steps for product BDD tests."""

import asyncio

from fastapi.testclient import TestClient
from pytest_bdd import given
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@given('a seller user exists')
def create_seller_user_for_product(step, client: TestClient, product_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    user_data = dict(zip(headers, values, strict=True))
    
    # Create the seller user
    response = client.post('/api/users', json={
        'email': user_data['email'],
        'password': user_data['password'],
        'name': user_data['name'],
        'role': user_data['role'],
    })
    
    assert response.status_code == 201, f"Failed to create seller user: {response.text}"
    created_user = response.json()
    
    # Store the seller_id for use in product creation
    product_state['seller_id'] = created_user['id']
    product_state['seller_user'] = created_user


@given('a product exists')
def product_exists(step, client: TestClient, product_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    row_data = dict(zip(headers, values, strict=True))
    
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'seller_id': int(row_data['seller_id']),
        'is_active': row_data['is_active'].lower() == 'true'
    }
    
    response = client.post('/api/products', json=request_data)
    assert response.status_code == 201, f"Failed to create product: {response.text}"
    
    product_data = response.json()
    product_state['product_id'] = product_data['id']
    product_state['original_product'] = product_data
    product_state['request_data'] = request_data


@given('a product exists with:')
def product_exists_with_status(step, client: TestClient, product_state):
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    row_data = dict(zip(headers, values, strict=True))
    
    # First create a seller user if needed
    seller_id = int(row_data['seller_id'])
    user_response = client.post('/api/users', json={
        'email': f'seller{seller_id}@test.com',
        'password': 'password123',
        'name': f'Test Seller {seller_id}',
        'role': 'seller',
    })
    
    if user_response.status_code == 201:
        seller_id = user_response.json()['id']
    
    # Create the product
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'price': int(row_data['price']),
        'seller_id': seller_id,
        'is_active': row_data['is_active'].lower() == 'true'
    }
    
    response = client.post('/api/products', json=request_data)
    assert response.status_code == 201, f"Failed to create product: {response.text}"
    
    product_data = response.json()
    product_state['product_id'] = product_data['id']
    
    # If status is not 'available', need to update it directly in database
    if 'status' in row_data and row_data['status'] != 'available':
        # Update status directly in database for test purposes
        async def update_product_status():
            TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE products SET status = :status WHERE id = :id"),
                    {"status": row_data['status'], "id": product_data['id']}
                )
            await engine.dispose()
        
        asyncio.run(update_product_status())
        product_data['status'] = row_data['status']
    
    product_state['original_product'] = product_data
    product_state['request_data'] = request_data


@given('a seller with products:')
def create_seller_with_products(step, client: TestClient, product_state):
    seller_response = client.post('/api/users', json={
        'email': 'list_seller@test.com',
        'password': 'password123',
        'name': 'List Test Seller',
        'role': 'seller',
    })
    
    if seller_response.status_code == 201:
        seller_id = seller_response.json()['id']
    else:
        seller_id = 1
    
    product_state['seller_id'] = seller_id
    product_state['created_products'] = []
    
    # Create products from table
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        product_data = dict(zip(headers, values, strict=True))
        
        # Create product
        create_response = client.post('/api/products', json={
            'name': product_data['name'],
            'description': product_data['description'],
            'price': int(product_data['price']),
            'seller_id': seller_id,
            'is_active': product_data['is_active'].lower() == 'true'
        })
        
        if create_response.status_code == 201:
            created_product = create_response.json()
            product_id = created_product['id']
            
            # Update status if not available
            if product_data['status'] != 'available':
                async def update_status(status, pid):
                    TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
                    engine = create_async_engine(TEST_DATABASE_URL)
                    async with engine.begin() as conn:
                        await conn.execute(
                            text("UPDATE products SET status = :status WHERE id = :id"),
                            {"status": status, "id": pid}
                        )
                    await engine.dispose()
                
                asyncio.run(update_status(product_data['status'], product_id))
                created_product['status'] = product_data['status']
            
            product_state['created_products'].append(created_product)


@given('no available products exist')
def create_no_available_products(step, client: TestClient, product_state):
    seller_response = client.post('/api/users', json={
        'email': 'empty_list_seller@test.com',
        'password': 'password123',
        'name': 'Empty List Seller',
        'role': 'seller',
    })
    
    if seller_response.status_code == 201:
        seller_id = seller_response.json()['id']
    else:
        seller_id = 1
    
    product_state['seller_id'] = seller_id
    product_state['created_products'] = []
    
    # Create non-available products from table
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        product_data = dict(zip(headers, values, strict=True))
        
        # Create product
        create_response = client.post('/api/products', json={
            'name': product_data['name'],
            'description': product_data['description'],
            'price': int(product_data['price']),
            'seller_id': seller_id,
            'is_active': product_data['is_active'].lower() == 'true'
        })
        
        if create_response.status_code == 201:
            created_product = create_response.json()
            product_id = created_product['id']
            
            # Update status to non-available
            async def update_status(status, pid):
                TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db"
                engine = create_async_engine(TEST_DATABASE_URL)
                async with engine.begin() as conn:
                    await conn.execute(
                        text("UPDATE products SET status = :status WHERE id = :id"),
                        {"status": status, "id": pid}
                    )
                await engine.dispose()
            
            asyncio.run(update_status(product_data['status'], product_id))
            created_product['status'] = product_data['status']
            
            product_state['created_products'].append(created_product)
