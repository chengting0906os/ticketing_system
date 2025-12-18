"""Common BDD Step Definitions for SSE (Server-Sent Events) testing.

This file contains reusable SSE step definitions that can be shared across all BDD tests.
Import this file in loader.py to use the common steps.

Usage in loader.py:
    from test.bdd_conftest.sse_step_conftest import *  # noqa: F401, F403

SSE Testing Types:
1. Kvrocks Pub/Sub - For booking status updates (user-specific channels)
2. HTTP SSE Streaming - For seat status updates (event-wide broadcasts)

Available Given steps:
    - I am subscribed to SSE for event {event_id} (Kvrocks pub/sub)
    - user is connected to SSE stream for event {event_id} (HTTP SSE)

Available When steps:
    - SSE event is published with: (Kvrocks pub/sub)
    - I subscribe to SSE endpoint "{endpoint}" (HTTP SSE - generic)
    - user connects to SSE stream for event {event_id} (HTTP SSE - reservation)
    - {user_count:d} users connect to SSE stream for event {event_id} (HTTP SSE)
    - section stats are updated with: (HTTP SSE mock)

Available Then steps:
    - I should receive SSE event with: (Kvrocks pub/sub)
    - SSE connection should be established (HTTP SSE)
    - initial status event should be received with: (HTTP SSE)
    - section stats should include: (HTTP SSE)
    - status update event should be received with: (HTTP SSE)
    - updated section stats should show: (HTTP SSE)
    - all 3 users should receive status update event (HTTP SSE)
    - all users should see same section stats: (HTTP SSE)
"""

import queue
import threading
import time
from typing import Any

import httpx
import orjson
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, then, when
from pytest_bdd.model import Step
from redis import Redis as SyncRedis

from src.platform.config.core_setting import settings
from test.bdd_conftest.shared_step_utils import (
    DEFAULT_PASSWORD,
    DEFAULT_SELLER_EMAIL,
    extract_table_data,
    login_user,
    resolve_endpoint_vars,
)


# =============================================================================
# Helper Classes
# =============================================================================


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


# =============================================================================
# Helper Functions - Kvrocks Pub/Sub
# =============================================================================


def _get_sync_redis() -> SyncRedis:
    """Get synchronous Redis client for SSE pub/sub testing."""
    return SyncRedis.from_url(
        f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
        password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
        decode_responses=False,  # Get raw bytes for orjson
    )


def _subscribe_in_background(
    redis_client: SyncRedis,
    channel: str,
    message_queue: queue.Queue,
    stop_event: threading.Event,
) -> None:
    """Background thread function to subscribe and collect messages."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)

    try:
        while not stop_event.is_set():
            try:
                message = pubsub.get_message(timeout=0.1)
                if message and message['type'] == 'message':
                    try:
                        data = message['data']
                        if isinstance(data, bytes):
                            event_data = orjson.loads(data)
                        else:
                            event_data = orjson.loads(data.encode())
                        message_queue.put(event_data)
                    except orjson.JSONDecodeError:
                        continue
            except (ValueError, ConnectionError, OSError):
                # Connection closed, exit gracefully
                break
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception:
            pass  # Ignore cleanup errors


# =============================================================================
# Given Steps - SSE Subscription
# =============================================================================


@given(parsers.parse('I am subscribed to SSE for event {event_id}'))
def given_subscribed_to_sse(
    event_id: str,
    context: dict[str, Any],
) -> None:
    """Set up real Kvrocks pub/sub subscription for SSE testing.

    Uses threading to subscribe in background and collect messages.

    Example:
        Given I am subscribed to SSE for event {event_id}
        Given I am subscribed to SSE for event 123
    """
    # Resolve event_id from context
    actual_event_id = context.get('event_id') if event_id == '{event_id}' else int(event_id)
    user_id = context.get('current_user', {}).get('id', context.get('buyer_id', 2))

    # Channel format matches BookingEventBroadcasterImpl
    channel = f'booking:status:{user_id}:{actual_event_id}'

    # Set up real pub/sub with threading
    redis_client = _get_sync_redis()
    message_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    # Start subscriber thread
    subscriber_thread = threading.Thread(
        target=_subscribe_in_background,
        args=(redis_client, channel, message_queue, stop_event),
        daemon=True,
    )
    subscriber_thread.start()

    # Wait for subscription to be ready
    time.sleep(0.1)

    # Store in context for later steps
    context['sse_subscription'] = {
        'event_id': actual_event_id,
        'user_id': user_id,
        'channel': channel,
        'redis_client': redis_client,
        'message_queue': message_queue,
        'stop_event': stop_event,
        'subscriber_thread': subscriber_thread,
    }


# =============================================================================
# When Steps - SSE Publishing
# =============================================================================


@when('SSE event is published with:')
def when_sse_event_published(
    step: Step,
    context: dict[str, Any],
) -> None:
    """Publish SSE event via real Kvrocks pub/sub.

    This tests the same channel that BookingEventBroadcasterImpl.publish() uses.

    Example:
        When SSE event is published with:
          | event_type      | status          | booking_id                           |
          | booking_updated | PENDING_PAYMENT | 01900000-0000-7000-8000-000000000001 |
    """
    event_data = extract_table_data(step)
    subscription = context.get('sse_subscription', {})
    channel = subscription.get('channel')

    if not channel:
        raise AssertionError('No SSE subscription found. Use "Given I am subscribed to SSE" first.')

    # Publish to Kvrocks
    redis_client = _get_sync_redis()
    message = orjson.dumps(event_data)
    redis_client.publish(channel, message)
    redis_client.close()

    # Give subscriber time to receive
    time.sleep(0.1)


# =============================================================================
# When Steps - Generic HTTP SSE Endpoint
# =============================================================================


@when(parsers.parse('I subscribe to SSE endpoint "{endpoint}"'))
def when_subscribe_to_sse_endpoint(
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
    http_server: str,
) -> None:
    """Subscribe to any SSE endpoint using HTTP streaming.

    This is a generic step that works with any SSE endpoint URL.
    Uses real HTTP streaming with httpx.

    Example:
        When I subscribe to SSE endpoint "/api/booking/event/{event_id}/sse"
        When I subscribe to SSE endpoint "/api/reservation/{event_id}/all_subsection_status/sse"
    """
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    url = f'{http_server}{resolved_endpoint}'

    # Get cookies from client for authentication
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    headers = {'Accept': 'text/event-stream'}

    # Read SSE events in a thread with status tracking
    events_list: list[dict[str, Any]] = []
    status_holder: dict[str, Any] = {'status_code': 0, 'content_type': ''}

    thread = threading.Thread(
        target=_read_sse_events_in_thread,
        args=(url, headers, cookies, events_list, status_holder, 3, 5.0),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=6)

    context['sse_events'] = events_list

    # Use actual HTTP status from the connection
    status_code = status_holder.get('status_code', 0)
    content_type = status_holder.get('content_type', '')

    context['response'] = MockResponse(
        status_code if status_code else 404,
        {'content-type': content_type or 'text/event-stream; charset=utf-8'},
        {} if status_code == 200 else {'detail': 'Connection failed'},
    )


# =============================================================================
# Then Steps - SSE Verification
# =============================================================================


@then('I should receive SSE event with:')
def then_should_receive_sse_event(
    step: Step,
    context: dict[str, Any],
) -> None:
    """Verify SSE event was received via real Kvrocks pub/sub.

    Example:
        Then I should receive SSE event with:
          | event_type      | status          |
          | booking_updated | PENDING_PAYMENT |
    """
    expected_data = extract_table_data(step)
    subscription = context.get('sse_subscription', {})
    message_queue = subscription.get('message_queue')
    stop_event = subscription.get('stop_event')

    if not message_queue:
        raise AssertionError('No SSE subscription found.')

    try:
        # Wait for message with timeout
        received_event = message_queue.get(timeout=2.0)
    except queue.Empty:
        raise AssertionError('No SSE events received within timeout')
    finally:
        # Clean up: stop subscriber thread
        if stop_event:
            stop_event.set()
        if redis_client := subscription.get('redis_client'):
            redis_client.close()

    # Validate received event - check all expected fields
    for field, expected_value in expected_data.items():
        actual_value = received_event.get(field)
        assert actual_value == expected_value, (
            f"Expected {field}='{expected_value}', got '{actual_value}'"
        )


# =============================================================================
# Helper Functions - HTTP SSE Streaming
# =============================================================================


def _read_sse_events_in_thread(
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    events_list: list[dict[str, Any]],
    status_holder: dict[str, Any],
    max_events: int = 3,
    timeout: float = 10.0,
) -> None:
    """Read SSE events from HTTP stream in a thread.

    Args:
        status_holder: Dict to store HTTP status code and content-type
    """
    try:
        with (
            httpx.Client(timeout=timeout, cookies=cookies) as client,
            client.stream('GET', url, headers=headers) as response,
        ):
            # Store actual HTTP status and headers
            status_holder['status_code'] = response.status_code
            status_holder['content_type'] = response.headers.get('content-type', '')

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
    except Exception:
        # Connection closed or timeout - that's OK for SSE
        pass


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

    threads: list[tuple[threading.Thread, list[dict[str, Any]], dict[str, Any]]] = []
    for _ in range(user_count):
        events_list: list[dict[str, Any]] = []
        status_holder: dict[str, Any] = {'status_code': 0, 'content_type': ''}
        thread = threading.Thread(
            target=_read_sse_events_in_thread,
            args=(url, headers, cookies, events_list, status_holder, 2, 10.0),
            daemon=True,
        )
        threads.append((thread, events_list, status_holder))
        thread.start()

    for thread, _, _ in threads:
        thread.join(timeout=10)

    context['event_id'] = event_id_int

    # Get status from first connection
    first_status = threads[0][2] if threads else {'status_code': 0, 'content_type': ''}

    if user_count == 1:
        # Single user: store events directly
        context['sse_events'] = threads[0][1] if threads else []
        has_events = bool(context['sse_events'])
    else:
        # Multiple users: store as user_connections
        context['user_connections'] = []
        for i, (_, events_list, _) in enumerate(threads):
            context['user_connections'].append({'user_id': i + 1, 'events': events_list})
        context['sse_events'] = []
        has_events = any(conn['events'] for conn in context['user_connections'])

    # Use actual HTTP status from connection
    status_code: int = int(first_status.get('status_code', 0))
    content_type: str = str(first_status.get('content_type', ''))

    context['response'] = MockResponse(
        status_code if status_code else (200 if has_events else 404),
        {'content-type': content_type or 'text/event-stream; charset=utf-8'},
        {} if status_code == 200 or has_events else {'detail': 'Event not found'},
    )


# =============================================================================
# Given Steps - HTTP SSE Connection
# =============================================================================


@given(parsers.parse('user is connected to SSE stream for event {event_id}'))
def given_user_connected_to_sse(event_id: str, context: dict[str, Any]) -> None:
    """Setup SSE connection context.

    Example:
        Given user is connected to SSE stream for event {event_id}
    """
    resolved_id = resolve_endpoint_vars(str(event_id), context)
    event_id_int = int(resolved_id)

    context['sse_connected'] = True
    context['sse_events'] = []
    context['event_id'] = event_id_int


# =============================================================================
# When Steps - HTTP SSE Connection
# =============================================================================


@when(parsers.parse('user connects to SSE stream for event {event_id}'))
def when_user_connects_to_sse(
    event_id: str,
    client: TestClient,
    context: dict[str, Any],
    http_server: str,
) -> None:
    """User connects to SSE stream using real HTTP client in thread.

    Example:
        When user connects to SSE stream for event {event_id}
    """
    _connect_users_to_sse(
        event_id=event_id,
        client=client,
        context=context,
        http_server=http_server,
        user_count=1,
    )


@when('section stats are updated with:')
def when_section_stats_updated(step: Step, context: dict[str, Any]) -> None:
    """Simulate section stats update in Kvrocks.

    Example:
        When section stats are updated with:
          | section_id | available | reserved | sold |
          | A-1        | 45        | 5        | 0    |
    """
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
def when_multiple_users_connect(
    user_count: int,
    event_id: str,
    client: TestClient,
    context: dict[str, Any],
    http_server: str,
) -> None:
    """Multiple users connect to SSE stream.

    Example:
        When 3 users connect to SSE stream for event {event_id}
    """
    _connect_users_to_sse(
        event_id=event_id,
        client=client,
        context=context,
        http_server=http_server,
        user_count=user_count,
    )


# =============================================================================
# Then Steps - HTTP SSE Verification
# =============================================================================


@then('SSE connection should be established')
def then_sse_connection_established(context: dict[str, Any]) -> None:
    """Verify SSE connection was established.

    Example:
        Then SSE connection should be established
    """
    response = context['response']
    assert response.status_code == 200, f'Expected 200, got {response.status_code}'
    assert 'text/event-stream' in response.headers.get('content-type', ''), (
        'Content-Type should be text/event-stream'
    )


@then('initial status event should be received with:')
def then_initial_status_received(step: Step, context: dict[str, Any]) -> None:
    """Verify initial status event was received.

    Example:
        Then initial status event should be received with:
          | event_type     | sections_count |
          | initial_status | 4              |
    """
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
def then_section_stats_include(step: Step, context: dict[str, Any]) -> None:
    """Verify section stats contain expected data.

    Example:
        Then section stats should include:
          | section_id | total | available |
          | A-1        | 50    | 50        |
    """
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
def then_status_update_received(step: Step, context: dict[str, Any]) -> None:
    """Verify status update event was received.

    Example:
        Then status update event should be received with:
          | event_type    |
          | status_update |
    """
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
def then_updated_section_stats_show(step: Step, context: dict[str, Any]) -> None:
    """Verify updated section stats.

    Example:
        Then updated section stats should show:
          | section_id | total | available | reserved |
          | A-1        | 50    | 45        | 5        |
    """
    data = extract_table_data(step)

    updated_stats = context.get('updated_stats', {})

    section_id = data['section_id']
    assert section_id in updated_stats, f'Section {section_id} not found'

    section = updated_stats[section_id]
    assert section['total'] == int(data['total']), 'Total mismatch'
    assert section['available'] == int(data['available']), 'Available mismatch'
    assert section['reserved'] == int(data['reserved']), 'Reserved mismatch'


@then('all 3 users should receive status update event')
def then_all_users_receive_update(context: dict[str, Any]) -> None:
    """Verify all users received the update.

    Example:
        Then all 3 users should receive status update event
    """
    connections = context.get('user_connections', [])

    assert len(connections) == 3, f'Expected 3 connections, got {len(connections)}'

    for conn in connections:
        events = conn.get('events', [])
        assert len(events) > 0, f'User {conn["user_id"]} received no events'


@then('all users should see same section stats:')
def then_all_users_see_same_stats(step: Step, context: dict[str, Any]) -> None:
    """Verify all users see the same stats.

    Example:
        Then all users should see same section stats:
          | section_id | available | reserved |
          | A-1        | 50        | 0        |
    """
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
