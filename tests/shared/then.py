"""Shared then steps for all BDD tests."""

from pytest_bdd import then


def get_state_with_response(user_state=None, product_state=None, order_state=None):
    for state in [order_state, product_state, user_state]:
        if state and state.get('response'):
            return state
    # If no state has response, return the first non-None state
    return order_state or product_state or user_state or {}


@then('get 200')
def verify_status_200(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@then('get 201')
def verify_status_201(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    if response.status_code != 201:
        print(f"Expected 201, got {response.status_code}")
        print(f"Response body: {response.text}")
    assert response.status_code == 201


@then('get 400')
def verify_status_400(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == 400


@then('get 401')
def verify_status_401(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == 401


@then('get 403')
def verify_status_403(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == 403


@then('get 404')
def verify_status_404(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == 404


@then('get 204')
def verify_status_204(user_state=None, product_state=None, order_state=None):
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == 204
