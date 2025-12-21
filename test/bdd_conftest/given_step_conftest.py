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


# ============ Given Steps - Login ============


def _get_role_defaults(role: str) -> tuple[str, str]:
    """Get default email and name for role."""
    if role == 'seller':
        return DEFAULT_SELLER_EMAIL, DEFAULT_SELLER_NAME
    return DEFAULT_BUYER_EMAIL, DEFAULT_BUYER_NAME


def _login_as_role_with_defaults(
    role: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Internal helper to login as role with default credentials."""
    email, name = _get_role_defaults(role)
    create_user_if_not_exists(client, email, DEFAULT_PASSWORD, name, role)
    user = login_user(client, email, DEFAULT_PASSWORD)
    store_user_in_context(user, role, context)


@given('I am logged in as a seller')
def given_logged_in_as_seller(client: TestClient, context: dict[str, Any]) -> None:
    """Login as seller with default credentials."""
    _login_as_role_with_defaults('seller', client, context)


@given('I am logged in as a buyer')
def given_logged_in_as_buyer(client: TestClient, context: dict[str, Any]) -> None:
    """Login as buyer with default credentials."""
    _login_as_role_with_defaults('buyer', client, context)


@given(parsers.parse('I am logged in as a {role} with'))
def given_logged_in_as_role_with_table(
    step: Step,
    role: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create and login as specified role with table credentials.

    Example:
        Given I am logged in as a seller with
            | email           | password | name        |
            | seller@test.com | P@ssw0rd | Test Seller |
    """
    assert role in ('seller', 'buyer'), f'Invalid role: {role}'
    data = extract_table_data(step)
    default_email, default_name = _get_role_defaults(role)

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


def _create_role_with_defaults(
    role: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Internal helper to create user with role-based defaults."""
    email, name = _get_role_defaults(role)

    user = create_user_if_not_exists(client, email, DEFAULT_PASSWORD, name, role)
    if not user:
        user = login_user(client, email, DEFAULT_PASSWORD)
    store_user_in_context(user, role, context, set_as_current=False)


@given(parsers.parse('a {role} exists'))
def given_role_exists(
    role: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Create a user with specified role using default credentials.

    Example:
        Given a seller exists
        Given a buyer exists
    """
    _create_role_with_defaults(role, client, context)


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
