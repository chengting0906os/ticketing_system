"""Shared then steps for all BDD tests."""

from pytest_bdd import then


@then('get 200')
def verify_status_200(user_state, product_state):
    """Verify successful operation with 200 status code."""
    # Use product_state if available, otherwise user_state
    state = product_state if product_state.get('response') else user_state
    response = state['response']
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@then('get 201')
def verify_status_201(user_state, product_state):
    """Verify successful creation with 201 status code."""
    # Use product_state if available, otherwise user_state
    state = product_state if product_state.get('response') else user_state
    response = state['response']
    if response.status_code != 201:
        print(f"Expected 201, got {response.status_code}")
        print(f"Response body: {response.text}")
    assert response.status_code == 201


@then('get 400')
def verify_status_400(user_state, product_state):
    """Verify bad request with 400 status code."""
    # Use product_state if available, otherwise user_state
    state = product_state if product_state.get('response') else user_state
    response = state['response']
    assert response.status_code == 400


@then('get 401')
def verify_status_401(user_state, product_state):
    """Verify unauthorized with 401 status code."""
    # Use product_state if available, otherwise user_state
    state = product_state if product_state.get('response') else user_state
    response = state['response']
    assert response.status_code == 401


@then('get 404')
def verify_status_404(user_state, product_state):
    """Verify not found with 404 status code."""
    # Use product_state if available, otherwise user_state
    state = product_state if product_state.get('response') else user_state
    response = state['response']
    assert response.status_code == 404
