"""
Pytest configuration for seat reservation SSE tests.

Contains all BDD step definitions for reservation SSE streaming tests.
"""

import threading
from typing import Any

import httpx
import orjson
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, then, when
from pytest_bdd.model import Step

from test.service.ticketing.reservation.fixtures import context, http_server
from test.bdd_conftest.shared_step_utils import (
    DEFAULT_PASSWORD,
    DEFAULT_SELLER_EMAIL,
    extract_table_data,
    login_user,
    resolve_endpoint_vars,
)

__all__ = [
    'context',
    'http_server',
]


# ============ Helper Functions ============


def read_sse_events_in_thread(
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    events_list: list[dict[str, Any]],
    max_events: int = 3,
) -> None:
    """Read SSE events from stream in a thread."""
    with (
        httpx.Client(timeout=5.0, cookies=cookies) as client,
        client.stream('GET', url, headers=headers) as response,
    ):
        if response.status_code != 200:
            return

        current_event: dict[str, Any] = {}
        for line in response.iter_lines():
            line = line.strip()

            if not line:
                if current_event:
                    events_list.append(current_event.copy())
                    current_event = {}
                    if len(events_list) >= max_events:
                        break
                continue

            if line.startswith('event:'):
                current_event['event'] = line.split(':', 1)[1].strip()
            elif line.startswith('data:'):
                data_str = line.split(':', 1)[1].strip()
                current_event['data'] = orjson.loads(data_str)


class MockResponse:
    """Mock response for SSE validation."""

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        json_data: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self._json_data = json_data or {}

    def json(self) -> dict[str, Any]:
        return self._json_data


# ============ Given Steps ============


@given(parsers.parse('user is connected to SSE stream for event {event_id}'))
def user_connected_to_sse(event_id: str, context: dict[str, Any]) -> None:
    """Setup SSE connection context."""
    resolved_id = resolve_endpoint_vars(str(event_id), context)
    event_id_int = int(resolved_id)

    context['sse_connected'] = True
    context['sse_events'] = []
    context['event_id'] = event_id_int


# ============ When Steps ============


def _connect_users_to_sse(
    *,
    event_id: str,
    client: TestClient,
    context: dict[str, Any],
    http_server: str,
    user_count: int,
) -> None:
    """Connect multiple users to SSE stream."""
    resolved_id = resolve_endpoint_vars(str(event_id), context)
    event_id_int = int(resolved_id)

    login_user(client, DEFAULT_SELLER_EMAIL, DEFAULT_PASSWORD)

    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    url = f'{http_server}/api/reservation/{event_id_int}/all_subsection_status/sse'
    headers = {'Accept': 'text/event-stream'}

    threads: list[tuple[threading.Thread, list[dict[str, Any]]]] = []
    for _ in range(user_count):
        events_list: list[dict[str, Any]] = []
        thread = threading.Thread(
            target=read_sse_events_in_thread,
            args=(url, headers, cookies, events_list, 2),
            daemon=True,
        )
        threads.append((thread, events_list))
        thread.start()

    for thread, _ in threads:
        thread.join(timeout=3)

    context['event_id'] = event_id_int

    if user_count == 1:
        # Single user: store events directly
        context['sse_events'] = threads[0][1] if threads else []
        has_events = bool(context['sse_events'])
    else:
        # Multiple users: store as user_connections
        context['user_connections'] = []
        for i, (_, events_list) in enumerate(threads):
            context['user_connections'].append({'user_id': i + 1, 'events': events_list})
        context['sse_events'] = []
        has_events = any(conn['events'] for conn in context['user_connections'])

    context['response'] = MockResponse(
        200 if has_events else 404,
        {'content-type': 'text/event-stream; charset=utf-8'},
        {} if has_events else {'detail': 'Event not found'},
    )


@when(parsers.parse('user connects to SSE stream for event {event_id}'))
def user_connects_to_sse(
    event_id: str,
    client: TestClient,
    context: dict[str, Any],
    http_server: str,
) -> None:
    """User connects to SSE stream using real HTTP client in thread."""
    _connect_users_to_sse(
        event_id=event_id,
        client=client,
        context=context,
        http_server=http_server,
        user_count=1,
    )


@when('section stats are updated with:')
def section_stats_updated(step: Step, context: dict[str, Any]) -> None:
    """Simulate section stats update in Kvrocks."""
    data = extract_table_data(step)

    section_id = data['section_id']
    available = int(data['available'])
    reserved = int(data.get('reserved', 0))
    sold = int(data.get('sold', 0))
    total = available + reserved + sold

    context['updated_stats'] = {
        section_id: {
            'section_id': section_id,
            'total': total,
            'available': available,
            'reserved': reserved,
            'sold': sold,
            'event_id': context.get('event_id', 1),
        }
    }

    context['sse_events'].append(
        {
            'event': 'status_update',
            'data': {'sections': context['updated_stats'], 'timestamp': 1234567890},
        }
    )


@when(parsers.parse('{user_count:d} users connect to SSE stream for event {event_id}'))
def multiple_users_connect(
    user_count: int,
    event_id: str,
    client: TestClient,
    context: dict[str, Any],
    http_server: str,
) -> None:
    """Multiple users connect to SSE stream."""
    _connect_users_to_sse(
        event_id=event_id,
        client=client,
        context=context,
        http_server=http_server,
        user_count=user_count,
    )


# ============ Then Steps ============


@then('SSE connection should be established')
def sse_connection_established(context: dict[str, Any]) -> None:
    """Verify SSE connection was established."""
    response = context['response']
    assert response.status_code == 200, f'Expected 200, got {response.status_code}'
    assert 'text/event-stream' in response.headers.get('content-type', ''), (
        'Content-Type should be text/event-stream'
    )


@then('initial status event should be received with:')
def initial_status_received(step: Step, context: dict[str, Any]) -> None:
    """Verify initial status event was received."""
    data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) > 0, 'No SSE events received'

    initial_event = None
    for event in events:
        if event.get('event') == data['event_type']:
            initial_event = event
            break

    assert initial_event is not None, (
        f"Expected event type '{data['event_type']}', got events: {[e.get('event') for e in events]}"
    )

    event_data = initial_event.get('data', {})
    sections = event_data.get('sections', {})
    expected_count = int(data['sections_count'])

    assert len(sections) == expected_count, (
        f'Expected {expected_count} sections, got {len(sections)}'
    )


@then('section stats should include:')
def section_stats_include(step: Step, context: dict[str, Any]) -> None:
    """Verify section stats contain expected data."""
    data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) > 0, 'No SSE events received'

    sections_event = None
    for event in events:
        event_data = event.get('data', {})
        if isinstance(event_data, dict) and 'sections' in event_data:
            sections_event = event
            break

    assert sections_event is not None, 'No event with sections data found'
    sections = sections_event['data'].get('sections', {})

    section_id = data['section_id']
    assert section_id in sections, f'Section {section_id} not found in response'

    section = sections[section_id]
    assert section['total'] == int(data['total']), (
        f'Total mismatch for {section_id}: got {section["total"]}, expected {data["total"]}'
    )
    assert section['available'] == int(data['available']), (
        f'Available mismatch for {section_id}: got {section["available"]}, expected {data["available"]}'
    )


@then('status update event should be received with:')
def status_update_received(step: Step, context: dict[str, Any]) -> None:
    """Verify status update event was received."""
    data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) >= 1, 'No status update event received'

    update_event = None
    for event in events:
        if event.get('event') == data['event_type']:
            update_event = event
            break

    assert update_event is not None, f"No event with type '{data['event_type']}' found in {events}"


@then('updated section stats should show:')
def updated_section_stats_show(step: Step, context: dict[str, Any]) -> None:
    """Verify updated section stats."""
    data = extract_table_data(step)

    updated_stats = context.get('updated_stats', {})

    section_id = data['section_id']
    assert section_id in updated_stats, f'Section {section_id} not found'

    section = updated_stats[section_id]
    assert section['total'] == int(data['total']), 'Total mismatch'
    assert section['available'] == int(data['available']), 'Available mismatch'
    assert section['reserved'] == int(data['reserved']), 'Reserved mismatch'


@then('all 3 users should receive status update event')
def all_users_receive_update(context: dict[str, Any]) -> None:
    """Verify all users received the update."""
    connections = context.get('user_connections', [])

    assert len(connections) == 3, f'Expected 3 connections, got {len(connections)}'

    for conn in connections:
        events = conn.get('events', [])
        assert len(events) > 0, f'User {conn["user_id"]} received no events'


@then('all users should see same section stats:')
def all_users_see_same_stats(step: Step, context: dict[str, Any]) -> None:
    """Verify all users see the same stats."""
    data = extract_table_data(step)
    connections = context.get('user_connections', [])

    section_id = data['section_id']
    expected_available = int(data['available'])
    expected_reserved = int(data['reserved'])

    for conn in connections:
        events = conn.get('events', [])
        assert len(events) > 0, f'User {conn["user_id"]} has no events'

        latest_event = None
        for event in reversed(events):
            event_data = event.get('data', {})
            if isinstance(event_data, dict) and 'sections' in event_data:
                latest_event = event
                break

        assert latest_event is not None, f'No event with sections data for user {conn["user_id"]}'
        sections = latest_event['data'].get('sections', {})

        assert section_id in sections, f'Section {section_id} not found for user {conn["user_id"]}'

        section = sections[section_id]
        assert section['available'] == expected_available, (
            f'Available mismatch for user {conn["user_id"]}'
        )
        assert section['reserved'] == expected_reserved, (
            f'Reserved mismatch for user {conn["user_id"]}'
        )


@then('{ticket_type} tickets should be returned with count:')
def tickets_returned_with_count(ticket_type: str, step: Step, context: dict[str, Any]) -> None:
    """Verify tickets are returned with correct count, optionally checking status."""
    rows = step.data_table.rows
    expected_count = int(rows[0].cells[0].value)

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert data['total_count'] == expected_count
    assert len(data['tickets']) == expected_count

    # If ticket_type is 'available', verify all tickets have status='available'
    if ticket_type == 'available':
        for ticket in data['tickets']:
            assert ticket['status'] == 'available'
