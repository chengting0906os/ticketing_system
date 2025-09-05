"""Then steps for product BDD tests."""

from pytest_bdd import then


@then('the product should be created with')
def verify_product_created(step, product_state):
    """Verify product was created with expected values."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    
    response = product_state['response']
    response_json = response.json()
    
    # Check each field in the expected data
    for field, expected_value in expected_data.items():
        if expected_value == '{any_int}':
            # Check that the field exists and is a positive integer
            assert field in response_json, f"Response should contain field '{field}'"
            assert isinstance(response_json[field], int), f"{field} should be an integer"
            assert response_json[field] > 0, f"{field} should be positive"
        elif field == 'is_active':
            expected_active = expected_value.lower() == 'true'
            assert response_json['is_active'] == expected_active
        elif field == 'status':
            assert response_json['status'] == expected_value
        elif field in ['price', 'seller_id', 'id']:
            assert response_json[field] == int(expected_value)
        else:
            assert response_json[field] == expected_value


@then('the stock should be initialized with')
def verify_stock_initialized(step, product_state):
    """Verify stock was initialized correctly."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    
    response = product_state['response']
    assert response.status_code == 201
    
    response_json = response.json()
    
    # Verify stock quantity (assuming the response includes stock info)
    if 'stock' in response_json:
        assert response_json['stock']['quantity'] == int(expected_data['quantity'])
    elif 'quantity' in response_json:
        assert response_json['quantity'] == int(expected_data['quantity'])




@then('the product should be updated with')
def verify_product_updated(step, product_state):
    """Verify product was updated with expected values."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    
    response = product_state['response']
    response_json = response.json()
    
    # Check each field in the expected data
    for field, expected_value in expected_data.items():
        if expected_value == '{any_int}':
            # Check that the field exists and is a positive integer
            assert field in response_json, f"Response should contain field '{field}'"
            assert isinstance(response_json[field], int), f"{field} should be an integer"
            assert response_json[field] > 0, f"{field} should be positive"
        elif field == 'is_active':
            expected_active = expected_value.lower() == 'true'
            assert response_json['is_active'] == expected_active
        elif field == 'status':
            assert response_json['status'] == expected_value
        elif field in ['price', 'seller_id', 'id']:
            assert response_json[field] == int(expected_value)
        else:
            assert response_json[field] == expected_value




@then('the error message should contain "Price must be positive"')
def verify_error_message(product_state):
    """Verify error message contains expected text."""
    response = product_state['response']
    response_json = response.json()
    
    # Check various possible error response formats
    error_msg = str(response_json)
    expected_message = "Price must be positive"
    assert expected_message in error_msg, f"Expected '{expected_message}' in error message, got: {error_msg}"


@then('the product should not exist')
def verify_product_not_exist(client, product_state):
    """Verify product no longer exists."""
    product_id = product_state['product_id']
    response = client.get(f'/api/products/{product_id}')
    assert response.status_code == 404


def _verify_error_contains(product_state, expected_text):
    """Helper function to verify error message contains expected text."""
    response = product_state['response']
    response_json = response.json()
    error_msg = str(response_json)
    assert expected_text in error_msg, f"Expected '{expected_text}' in error message, got: {error_msg}"


@then('the error message should contain "Cannot delete reserved product"')
def verify_cannot_delete_reserved(product_state):
    _verify_error_contains(product_state, "Cannot delete reserved product")


@then('the error message should contain "Cannot delete sold product"')
def verify_cannot_delete_sold(product_state):
    _verify_error_contains(product_state, "Cannot delete sold product")


def _verify_product_count(product_state, count):
    """Helper to verify product count."""
    response = product_state['response']
    assert response.status_code == 200
    products = response.json()
    assert len(products) == count, f"Expected {count} products, got {len(products)}"
    return products


@then('the seller should see 5 products')
def verify_seller_sees_5_products(product_state):
    _verify_product_count(product_state, 5)


@then('the buyer should see 2 products')
def verify_buyer_sees_2_products(product_state):
    products = _verify_product_count(product_state, 2)
    # Verify they are the active and available ones
    for p in products:
        assert p['is_active'] is True
        assert p['status'] == 'available'


@then('the buyer should see 0 products')
def verify_buyer_sees_0_products(product_state):
    _verify_product_count(product_state, 0)


@then('the products should include all statuses')
def verify_products_include_all_statuses(product_state):
    """Verify that products include different statuses."""
    response = product_state['response']
    products = response.json()
    
    statuses = {product['status'] for product in products}
    # Should have at least available, reserved, and sold
    expected_statuses = {'available', 'reserved', 'sold'}
    assert expected_statuses.issubset(statuses), f"Expected statuses {expected_statuses}, got {statuses}"


@then('the products should be:')
def verify_specific_products(step, product_state):
    """Verify specific products are in the list."""
    response = product_state['response']
    products = response.json()
    
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    
    expected_products = []
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_products.append(dict(zip(headers, values, strict=True)))
    
    # Verify we have the right number of products
    assert len(products) == len(expected_products), f"Expected {len(expected_products)} products, got {len(products)}"
    
    # Verify each expected product is present
    for expected in expected_products:
        found = False
        for product in products:
            if product['name'] == expected['name']:
                assert product['description'] == expected['description']
                assert str(product['price']) == expected['price']
                assert str(product['is_active']).lower() == expected['is_active'].lower()
                assert product['status'] == expected['status']
                found = True
                break
        assert found, f"Product {expected['name']} not found in response"
