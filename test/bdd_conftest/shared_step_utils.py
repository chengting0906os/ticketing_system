"""Shared utility functions for BDD step definitions.

This module contains common helper functions used by both When and Given step definitions.
"""

import json
import re
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response
import orjson
from pytest_bdd.model import Step

from src.platform.constant.route_constant import USER_CREATE, USER_LOGIN
from test.constants import DEFAULT_SEATING_CONFIG

# Default test credentials
DEFAULT_PASSWORD = 'P@ssw0rd'
DEFAULT_SELLER_EMAIL = 'seller@test.com'
DEFAULT_SELLER_NAME = 'Test Seller'
DEFAULT_BUYER_EMAIL = 'buyer@test.com'
DEFAULT_BUYER_NAME = 'Test Buyer'


# ============ State Management ============


def store_user_in_context(
    user: dict[str, Any],
    role: str,
    context: dict[str, Any],
    *,
    set_as_current: bool = True,
) -> None:
    """Store user info in context with role and optionally as current_user.

    Args:
        user: User data dict (should contain 'id')
        role: Role name like 'buyer', 'seller'
        context: The unified context dict
        set_as_current: If True, also store as 'current_user' (default True)
    """
    # Store by role
    context[role] = user
    if 'id' in user:
        context[f'{role}_id'] = user['id']

    # Also store as current_user for convenience
    if set_as_current:
        context['current_user'] = user
        if 'id' in user:
            context['current_user_id'] = user['id']


# ============ Table Data Extraction ============


def extract_table_data(step: Step) -> dict[str, str]:
    """Extract first row of table data as dict for BDD tests."""
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    return dict(zip(headers, values, strict=True))


def extract_single_value(step: Step) -> str:
    """Extract single value from a table (for simple | value | tables)."""
    rows = step.data_table.rows
    return rows[0].cells[0].value


def convert_table_values(data: dict[str, str]) -> dict[str, Any]:
    """Convert string values to appropriate types (int, bool, list, dict, etc.).

    Note: Empty strings are preserved as empty strings, not converted to None.
    Use 'none' or 'null' explicitly to get None value.
    Long numeric strings (>10 digits) like card numbers are kept as strings.
    JSON arrays like ["a","b"] or [] are parsed as lists.
    JSON objects like {"key": "value"} are parsed as dicts.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        value = value.strip()
        # Check for JSON array or object syntax first
        if (value.startswith('[') and value.endswith(']')) or (
            value.startswith('{') and value.endswith('}')
        ):
            try:
                result[key] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass  # Fall through to treat as string
        # Only convert short numeric strings to int (exclude card numbers, phone numbers, etc.)
        is_numeric = value.isdigit() or (value.startswith('-') and value[1:].isdigit())
        if is_numeric and len(value.lstrip('-')) <= 10:
            result[key] = int(value)
        elif value.lower() == 'true':
            result[key] = True
        elif value.lower() == 'false':
            result[key] = False
        elif value.lower() in ('none', 'null'):
            result[key] = None
        else:
            result[key] = value
    return result


# ============ Variable Resolution ============


def resolve_endpoint_vars(endpoint: str, context: dict[str, Any]) -> str:
    """Resolve variables like {user_id} or {event_id} in endpoint.

    Supports patterns like:
    - {user_id} -> looks for 'user_id' in context
    - {event.id} -> looks for 'event' dict in context, then 'id' key
    """
    pattern = r'\{([^}]+)\}'

    def replacer(match: re.Match[str]) -> str:
        key_path = match.group(1)

        # Handle nested keys like "event.id"
        if '.' in key_path:
            parts = key_path.split('.')
            obj = context
            for part in parts:
                if isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                elif hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    return match.group(0)  # Keep original if not found
            return str(obj)

        # Simple key lookup
        if key_path in context:
            return str(context[key_path])

        return match.group(0)  # Keep original if not found

    return re.sub(pattern, replacer, endpoint)


def resolve_table_vars(data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Resolve variables like {event_id} in table data values.

    Supports the same patterns as resolve_endpoint_vars:
    - {user_id} -> looks for 'user_id' in context
    - {event.id} -> looks for 'event' dict in context, then 'id' key
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = resolve_endpoint_vars(value, context)
        else:
            result[key] = value
    return result


# ============ User Management ============


def create_user_if_not_exists(
    client: TestClient,
    email: str,
    password: str,
    name: str,
    role: str,
) -> dict[str, Any] | None:
    """Create user via API, returns None if user already exists."""
    response = client.post(
        USER_CREATE,
        json={'email': email, 'password': password, 'name': name, 'role': role},
    )
    if response.status_code == 201:
        return response.json()
    return None


def login_user(client: TestClient, email: str, password: str) -> dict[str, Any]:
    """Login user and return response data.

    Clears existing auth cookies before login to avoid cookie conflicts.
    """
    # Clear existing auth cookies to avoid CookieConflict when logging in as different user
    client.cookies.clear()
    response = client.post(USER_LOGIN, json={'email': email, 'password': password})
    assert response.status_code == 200, f'Login failed: {response.text}'
    return response.json()


# Alias for backward compatibility
create_user = create_user_if_not_exists


# ============ Response Assertions ============


def assert_response_status(
    response: Response, expected_status: int, message: str | None = None
) -> None:
    """Assert response has expected status code."""
    response_text = getattr(response, 'text', getattr(response, 'content', 'N/A'))
    assert response.status_code == expected_status, (
        message or f'Expected {expected_status}, got {response.status_code}: {response_text}'
    )


# ============ Seating Config ============


def parse_seating_config(seating_config_str: str | None) -> dict[str, Any]:
    """Parse seating config JSON string, return default if invalid."""
    if not seating_config_str:
        return DEFAULT_SEATING_CONFIG
    try:
        return orjson.loads(seating_config_str)
    except (orjson.JSONDecodeError, TypeError):
        return DEFAULT_SEATING_CONFIG
