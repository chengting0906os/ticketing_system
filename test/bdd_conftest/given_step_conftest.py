"""Common BDD Step Definitions for pytest-bdd.

This file contains reusable "Given" step definitions that can be shared across all BDD tests.
Import this file in bdd_steps_loader.py to use the common steps.

Usage in bdd_steps_loader.py:
    from test.bdd_conftest.given_step_conftest import *  # noqa: F401, F403

Available Given steps:
    - I am logged in as a seller
    - I am logged in as a buyer
    - I am logged in as a seller with
    - I am logged in as a buyer with
    - I am logged in as "{role}"
    - I am logged in as "{role}" with
    - a seller exists:
    - a buyer exists:
"""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from pytest_bdd import given, parsers
from pytest_bdd.model import Step

from src.platform.constant.route_constant import EVENT_CREATE
from test.constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME, TEST_SELLER_EMAIL
from test.bdd_conftest.shared_step_utils import (
    DEFAULT_BUYER_EMAIL,
    DEFAULT_BUYER_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_SELLER_EMAIL,
    DEFAULT_SELLER_NAME,
    create_user_if_not_exists,
    extract_table_data,
    login_user,
    parse_seating_config,
    store_user_in_context,
)


# ============ Given Steps - Simple Login ============


@given('I am logged in as a seller')
def given_logged_in_as_seller(
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Login as default seller (creates if not exists).

    Example:
        Given I am logged in as a seller
    """
    create_user_if_not_exists(
        client, DEFAULT_SELLER_EMAIL, DEFAULT_PASSWORD, DEFAULT_SELLER_NAME, 'seller'
    )
    user = login_user(client, DEFAULT_SELLER_EMAIL, DEFAULT_PASSWORD)
    store_user_in_context(user, 'seller', context)


@given('I am logged in as a buyer')
def given_logged_in_as_buyer(
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Login as default buyer (creates if not exists).

    Example:
        Given I am logged in as a buyer
    """
    create_user_if_not_exists(
        client, DEFAULT_BUYER_EMAIL, DEFAULT_PASSWORD, DEFAULT_BUYER_NAME, 'buyer'
    )
    user = login_user(client, DEFAULT_BUYER_EMAIL, DEFAULT_PASSWORD)
    store_user_in_context(user, 'buyer', context)


# ============ Given Steps - Login with Table Data ============


@given('I am logged in as a seller with')
def given_logged_in_as_seller_with_table(
    step: Step,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create and login as seller with specified credentials.

    Example:
        Given I am logged in as a seller with
            | email           | password | name        |
            | seller@test.com | P@ssw0rd | Test Seller |
    """
    data = extract_table_data(step)
    email = data.get('email', DEFAULT_SELLER_EMAIL)
    password = data.get('password', DEFAULT_PASSWORD)
    name = data.get('name', DEFAULT_SELLER_NAME)

    create_user_if_not_exists(client, email, password, name, 'seller')
    user = login_user(client, email, password)
    store_user_in_context(user, 'seller', context)


@given('I am logged in as a buyer with')
def given_logged_in_as_buyer_with_table(
    step: Step,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create and login as buyer with specified credentials.

    Example:
        Given I am logged in as a buyer with
            | email          | password | name       |
            | buyer@test.com | P@ssw0rd | Test Buyer |
    """
    data = extract_table_data(step)
    email = data.get('email', DEFAULT_BUYER_EMAIL)
    password = data.get('password', DEFAULT_PASSWORD)
    name = data.get('name', DEFAULT_BUYER_NAME)

    create_user_if_not_exists(client, email, password, name, 'buyer')
    user = login_user(client, email, password)
    store_user_in_context(user, 'buyer', context)


# ============ Given Steps - User with Role Parameter ============


@given(parsers.parse('I am logged in as "{role}"'))
def given_logged_in_as_role(
    role: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Login as specified role with default credentials.

    Example:
        Given I am logged in as "seller"
        Given I am logged in as "buyer"
    """
    if role == 'seller':
        email, name = DEFAULT_SELLER_EMAIL, DEFAULT_SELLER_NAME
    else:
        email, name = DEFAULT_BUYER_EMAIL, DEFAULT_BUYER_NAME

    create_user_if_not_exists(client, email, DEFAULT_PASSWORD, name, role)
    user = login_user(client, email, DEFAULT_PASSWORD)
    store_user_in_context(user, role, context)


@given(parsers.parse('I am logged in as "{role}" with'))
def given_logged_in_as_role_with_table(
    step: Step,
    role: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create and login as specified role with table credentials.

    Example:
        Given I am logged in as "seller" with
            | email           | password | name        |
            | seller@test.com | P@ssw0rd | Test Seller |
    """
    data = extract_table_data(step)
    default_email = DEFAULT_SELLER_EMAIL if role == 'seller' else DEFAULT_BUYER_EMAIL
    default_name = DEFAULT_SELLER_NAME if role == 'seller' else DEFAULT_BUYER_NAME

    email = data.get('email', default_email)
    password = data.get('password', DEFAULT_PASSWORD)
    name = data.get('name', default_name)

    create_user_if_not_exists(client, email, password, name, role)
    user = login_user(client, email, password)
    store_user_in_context(user, role, context)


# ============ Given Steps - User Creation ============


@given('I am not authenticated')
def given_not_authenticated(client: TestClient) -> None:
    """Clear authentication cookies to simulate unauthenticated user.

    Example:
        Given I am not authenticated
    """
    client.cookies.clear()


@given('a seller exists')
def given_seller_exists_simple(
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create a seller with default credentials (no datatable).

    Example:
        Given a seller exists
    """
    user = create_user_if_not_exists(
        client, DEFAULT_SELLER_EMAIL, DEFAULT_PASSWORD, DEFAULT_SELLER_NAME, 'seller'
    )
    # If user already exists, get ID via login
    if not user:
        user = login_user(client, DEFAULT_SELLER_EMAIL, DEFAULT_PASSWORD)
    store_user_in_context(user, 'seller', context, set_as_current=False)


@given('a buyer exists')
def given_buyer_exists_simple(
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create a buyer with default credentials (no datatable).

    Example:
        Given a buyer exists
    """
    user = create_user_if_not_exists(
        client, DEFAULT_BUYER_EMAIL, DEFAULT_PASSWORD, DEFAULT_BUYER_NAME, 'buyer'
    )
    # If user already exists, get ID via login
    if not user:
        user = login_user(client, DEFAULT_BUYER_EMAIL, DEFAULT_PASSWORD)
    store_user_in_context(user, 'buyer', context, set_as_current=False)


# ============ Given Steps - Event Creation ============


@given('an event exists with:')
def create_event_shared(
    step: Step,
    client: TestClient,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> dict[str, Any]:
    """Create event via API - unified approach for all tests.

    Example:
        Given an event exists with:
            | name         | description | is_active | status    | venue_name   | seating_config |
            | Test Concert | Test event  | true      | available | Taipei Arena | {...}          |
    """
    event_data = extract_table_data(step)

    login_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD)
    request_data = {
        'name': event_data['name'],
        'description': event_data['description'],
        'is_active': event_data.get('is_active', 'true').lower() == 'true',
        'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
        'seating_config': parse_seating_config(
            event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON)
        ),
    }

    response = client.post(EVENT_CREATE, json=request_data)
    assert response.status_code == 201, f'Failed to create event: {response.text}'
    event_result = response.json()
    event_id = event_result['id']

    # If test specifies sold_out status, directly update the event status in database
    desired_status = event_data.get('status', 'available')
    if desired_status == 'sold_out':
        execute_sql_statement(
            'UPDATE event SET status = :status WHERE id = :id',
            {'status': 'sold_out', 'id': event_id},
        )

    event = {
        'id': event_id,
        'name': event_data['name'],
        'status': event_data.get('status', 'available'),
    }

    # Store event in context
    context['event'] = event
    context['event_id'] = event_id
    context['original_event'] = event

    return event
