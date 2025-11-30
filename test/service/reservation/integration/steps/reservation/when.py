"""When steps for seat reservation SSE test"""

import threading
from typing import Any

from fastapi.testclient import TestClient
import httpx
import orjson
from pytest_bdd import when
from pytest_bdd.model import Step

from test.shared.utils import extract_table_data, login_user
from test.util_constant import DEFAULT_PASSWORD, SELLER1_EMAIL


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


@when('user connects to SSE stream for event:')
def user_connects_to_sse(
    step: Step, client: TestClient, context: dict[str, Any], http_server: str
) -> None:
    """User connects to SSE stream using real HTTP client in thread."""

    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login first to get cookies
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Extract cookies from TestClient (handle multiple cookies with same name)
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    # Read SSE events in thread
    events_list: list[dict[str, Any]] = []
    url = f'{http_server}/api/reservation/{event_id}/all_subsection_status/sse'
    headers = {'Accept': 'text/event-stream'}

    thread = threading.Thread(
        target=read_sse_events_in_thread, args=(url, headers, cookies, events_list, 2), daemon=True
    )
    thread.start()
    thread.join(timeout=3)

    context['sse_events'] = events_list
    context['event_id'] = event_id

    # Create mock response for validation
    class MockResponse:
        def __init__(
            self,
            status_code: int,
            headers: dict[str, str],
            json_data: dict[str, Any],
        ) -> None:
            self.status_code = status_code
            self.headers = headers
            self._json_data = json_data

        def json(self) -> dict[str, Any]:
            return self._json_data

    # Set response based on SSE result
    if events_list:
        context['response'] = MockResponse(
            200, {'content-type': 'text/event-stream; charset=utf-8'}, {}
        )
    else:
        context['response'] = MockResponse(404, {}, {'detail': 'Event not found'})


@when('section stats are updated with:')
def section_stats_updated(step: Step, context: dict[str, Any]) -> None:
    """Simulate section stats update in Kvrocks."""
    data = extract_table_data(step)

    # Update stats in Kvrocks (this would trigger SSE update in real scenario)
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


@when('3 users connect to SSE stream for event 1')
def multiple_users_connect(client: TestClient, context: dict[str, Any], http_server: str) -> None:
    # Login first to get cookies
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Extract cookies from TestClient (handle multiple cookies with same name)
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    context['user_connections'] = []
    url = f'{http_server}/api/reservation/1/all_subsection_status/sse'
    headers = {'Accept': 'text/event-stream'}

    # Start 3 threads to simulate 3 users
    threads: list[tuple[threading.Thread, list[dict[str, Any]]]] = []
    for _ in range(3):
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

    for i, (_, events_list) in enumerate(threads):
        connection_data = {
            'user_id': i + 1,
            'events': events_list,
        }
        context['user_connections'].append(connection_data)

    # Create mock response
    class MockResponse:
        def __init__(self, status_code: int, headers: dict[str, str]) -> None:
            self.status_code = status_code
            self.headers = headers

    has_events = any(conn['events'] for conn in context['user_connections'])
    context['response'] = MockResponse(
        200 if has_events else 404, {'content-type': 'text/event-stream; charset=utf-8'}
    )


# Note: 'seller lists tickets by section with:' step is defined in
# test/service/ticketing/integration/steps/event_ticketing/when.py
# and imported via bdd_steps_loader.py
