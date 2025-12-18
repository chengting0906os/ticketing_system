"""Common BDD Step Definitions for pytest-bdd.

This file contains reusable "When" step definitions that can be shared across all BDD tests.
Import this file in bdd_steps_loader.py to use the common steps.

Usage in bdd_steps_loader.py:
    from test.bdd_conftest.when_step_conftest import *  # noqa: F401, F403

Available When steps:
    - I call POST "{endpoint}" with
    - I call POST "{endpoint}"
    - I call GET "{endpoint}"
    - I call PUT "{endpoint}" with
    - I call PATCH "{endpoint}" with
    - I call DELETE "{endpoint}"

Endpoint variable substitution:
    Endpoints can contain variables like {user_id} or {booking.id} which will be resolved
    from the context fixture.
    Example: "/api/booking/{booking.id}/cancel" -> "/api/booking/abc123/cancel"
"""

from typing import Any

from fastapi.testclient import TestClient
from pytest_bdd import parsers, when
from pytest_bdd.model import Step

from test.bdd_conftest.shared_step_utils import (
    convert_table_values,
    extract_table_data,
    resolve_endpoint_vars,
    resolve_table_vars,
)


# ============ When Steps ============


@when(parsers.parse('I call POST "{endpoint}" with'))
def when_call_post_with_data(
    step: Step,
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call POST API with table data.

    Example:
        When I call POST "/api/user/register" with
            | email              | password  | name     | role   |
            | test@example.com   | P@ssw0rd  | TestUser | buyer  |

    Variable substitution in table values:
        When I call POST "/api/booking" with
            | event_id   | section | quantity |
            | {event_id} | A       | 2        |
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    data = convert_table_values(extract_table_data(step))
    data = resolve_table_vars(data, context)
    response = client.post(resolved_endpoint, json=data)
    response_data = response.json() if response.content else None

    context['request_data'] = data
    context['response'] = response
    context['response_data'] = response_data

    # For POST operations that return created/updated entity
    if response_data:
        context['updated_booking'] = response_data
        context['updated_event'] = response_data
        if 'booking' not in context:
            context['booking'] = response_data
        if 'event' not in context:
            context['event'] = response_data


@when(parsers.parse('I call POST "{endpoint}"'))
def when_call_post_no_data(
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call POST API without data (e.g., for refresh actions).

    Example:
        When I call POST "/api/auth/refresh"
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    response = client.post(resolved_endpoint)
    context['response'] = response
    context['response_data'] = response.json() if response.content else None


@when(parsers.parse('I call GET "{endpoint}"'))
def when_call_get(
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call GET API.

    Example:
        When I call GET "/api/event/1"
        When I call GET "/api/event/{event_id}"
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    response = client.get(resolved_endpoint)
    response_data = response.json() if response.content else None

    context['response'] = response
    context['response_data'] = response_data

    if response_data:
        context['updated_booking'] = response_data
        context['updated_event'] = response_data


@when(parsers.parse('I call PUT "{endpoint}" with'))
def when_call_put_with_data(
    step: Step,
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call PUT API with table data.

    Example:
        When I call PUT "/api/event/1" with
            | name        | description   |
            | New Name    | New Desc      |
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    data = convert_table_values(extract_table_data(step))
    response = client.put(resolved_endpoint, json=data)
    context['response'] = response
    context['response_data'] = response.json() if response.content else None


@when(parsers.parse('I call PATCH "{endpoint}" with'))
def when_call_patch_with_data(
    step: Step,
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call PATCH API with table data.

    Example:
        When I call PATCH "/api/event/1" with
            | is_active |
            | false     |
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    data = convert_table_values(extract_table_data(step))
    response = client.patch(resolved_endpoint, json=data)
    context['response'] = response
    context['response_data'] = response.json() if response.content else None


@when(parsers.parse('I call PATCH "{endpoint}"'))
def when_call_patch_no_data(
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call PATCH API without data (e.g., for cancel actions).

    Example:
        When I call PATCH "/api/booking/{booking.id}/cancel"
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    response = client.patch(resolved_endpoint)
    response_data = response.json() if response.content else None

    context['response'] = response
    context['response_data'] = response_data

    if response_data:
        context['updated_booking'] = response_data
        context['updated_event'] = response_data


@when(parsers.parse('I call DELETE "{endpoint}"'))
def when_call_delete(
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call DELETE API.

    Example:
        When I call DELETE "/api/event/1"
        When I call DELETE "/api/event/{event_id}"
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    response = client.delete(resolved_endpoint)
    context['response'] = response
    context['response_data'] = response.json() if response.content else None
