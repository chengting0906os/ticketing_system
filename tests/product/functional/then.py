from pytest_bdd import then


@then('the product should be created with')
def verify_product_created(step, product_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    response = product_state['response']
    response_json = response.json()
    for field, expected_value in expected_data.items():
        if expected_value == '{any_int}':
            assert field in response_json, f"Response should contain field '{field}'"
            assert isinstance(response_json[field], int), f'{field} should be an integer'
            assert response_json[field] > 0, f'{field} should be positive'
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
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    response = product_state['response']
    assert response.status_code == 201
    response_json = response.json()
    if 'stock' in response_json:
        assert response_json['stock']['quantity'] == int(expected_data['quantity'])
    elif 'quantity' in response_json:
        assert response_json['quantity'] == int(expected_data['quantity'])


@then('the product should be updated with')
def verify_product_updated(step, product_state):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    response = product_state['response']
    response_json = response.json()
    for field, expected_value in expected_data.items():
        if expected_value == '{any_int}':
            assert field in response_json, f"Response should contain field '{field}'"
            assert isinstance(response_json[field], int), f'{field} should be an integer'
            assert response_json[field] > 0, f'{field} should be positive'
        elif field == 'is_active':
            expected_active = expected_value.lower() == 'true'
            assert response_json['is_active'] == expected_active
        elif field == 'status':
            assert response_json['status'] == expected_value
        elif field in ['price', 'seller_id', 'id']:
            assert response_json[field] == int(expected_value)
        else:
            assert response_json[field] == expected_value


@then('the product should not exist')
def verify_product_not_exist(client, product_state):
    product_id = product_state['product_id']
    response = client.get(f'/api/products/{product_id}')
    assert response.status_code == 404


def _verify_error_contains(product_state, expected_text):
    response = product_state['response']
    response_json = response.json()
    error_msg = str(response_json)
    assert expected_text in error_msg, (
        f"Expected '{expected_text}' in error message, got: {error_msg}"
    )


def _verify_product_count(product_state, count):
    response = product_state['response']
    assert response.status_code == 200
    products = response.json()
    assert len(products) == count, f'Expected {count} products, got {len(products)}'
    return products


@then('the seller should see 5 products')
def verify_seller_sees_5_products(product_state):
    _verify_product_count(product_state, 5)


@then('the buyer should see 2 products')
def verify_buyer_sees_2_products(product_state):
    products = _verify_product_count(product_state, 2)
    for p in products:
        assert p['is_active'] is True
        assert p['status'] == 'available'


@then('the buyer should see 0 products')
def verify_buyer_sees_0_products(product_state):
    _verify_product_count(product_state, 0)


@then('the products should include all statuses')
def verify_products_include_all_statuses(product_state):
    response = product_state['response']
    products = response.json()
    statuses = {product['status'] for product in products}
    expected_statuses = {'available', 'reserved', 'sold'}
    assert expected_statuses.issubset(statuses), (
        f'Expected statuses {expected_statuses}, got {statuses}'
    )


@then('the products should be:')
def verify_specific_products(step, product_state):
    response = product_state['response']
    products = response.json()
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    expected_products = []
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_products.append(dict(zip(headers, values, strict=True)))
    assert len(products) == len(expected_products), (
        f'Expected {len(expected_products)} products, got {len(products)}'
    )
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
        assert found, f'Product {expected["name"]} not found in response'
