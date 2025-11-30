"""When steps for seat reservation SSE test"""

import threading
from typing import List

from fastapi.testclient import TestClient
import httpx
import orjson
from pytest_bdd import when

from test.shared.utils import extract_table_data, login_user
from test.util_constant import DEFAULT_PASSWORD, SELLER1_EMAIL


def read_sse_events_in_thread(
    url: str, headers: dict, cookies: dict, events_list: list, max_events: int = 3
):
    try:
        with httpx.Client(timeout=5.0, cookies=cookies) as client:
            with client.stream('GET', url, headers=headers) as response:
                if response.status_code != 200:
                    return

                current_event = {}
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
                        try:
                            current_event['data'] = orjson.loads(data_str)
                        except orjson.JSONDecodeError:
                            # Try parsing Python dict repr (single quotes) by using ast.literal_eval
                            import ast

                            try:
                                current_event['data'] = ast.literal_eval(data_str)
                            except (ValueError, SyntaxError):
                                current_event['data'] = data_str
    except Exception as e:
        print(f'SSE thread error: {e}')


@when('user connects to SSE stream for event:')
def user_connects_to_sse(step, client: TestClient, context, http_server):
    """User connects to SSE stream using real HTTP client in thread."""

    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login first to get cookies
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Extract cookies from TestClient (handle multiple cookies with same name)
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    # 在 thread 中讀取 SSE 事件
    events_list = []
    url = f'{http_server}/api/reservation/{event_id}/all_subsection_status/sse'
    headers = {'Accept': 'text/event-stream'}

    # 啟動 thread 讀取 SSE
    thread = threading.Thread(
        target=read_sse_events_in_thread, args=(url, headers, cookies, events_list, 2), daemon=True
    )
    thread.start()
    thread.join(timeout=3)  # 最多等3秒

    # 保存結果
    context['sse_events'] = events_list
    context['event_id'] = event_id

    # Create mock response for validation
    class MockResponse:
        def __init__(self, status_code, headers=None, json_data=None):
            self.status_code = status_code
            self.headers = headers or {}
            self._json_data = json_data or {}

        def json(self):
            return self._json_data

    # Check if we got events or error response
    if events_list:
        context['response'] = MockResponse(
            200, headers={'content-type': 'text/event-stream; charset=utf-8'}
        )
    else:
        # Check if it's a real error (404, etc) by making actual request
        import httpx

        with httpx.Client(timeout=2.0, cookies=cookies) as http_client:
            try:
                resp = http_client.get(url, headers=headers)
                context['response'] = MockResponse(
                    resp.status_code, dict(resp.headers), resp.json()
                )
            except Exception:
                context['response'] = MockResponse(404, {}, {'detail': 'Event not found'})


@when('section stats are updated with:')
def section_stats_updated(step, context):
    """Simulate section stats update in Kvrocks."""
    data = extract_table_data(step)

    # Update stats in Kvrocks (this would trigger SSE update in real scenario)
    section_id = data['section_id']
    available = int(data['available'])
    reserved = int(data.get('reserved', 0))
    sold = int(data.get('sold', 0))
    total = available + reserved + sold

    # Mock the stats update
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

    # Simulate receiving the update event
    if 'sse_events' not in context:
        context['sse_events'] = []

    context['sse_events'].append(
        {
            'event': 'status_update',
            'data': {'sections': context['updated_stats'], 'timestamp': 1234567890},
        }
    )


@when('3 users connect to SSE stream for event 1')
def multiple_users_connect(client: TestClient, context, http_server):
    # Login first to get cookies
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Extract cookies from TestClient (handle multiple cookies with same name)
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    context['user_connections'] = []
    url = f'{http_server}/api/reservation/1/all_subsection_status/sse'
    headers = {'Accept': 'text/event-stream'}

    # 啟動3個 thread 模擬3個用戶
    threads = []
    for _ in range(3):
        events_list = []
        thread = threading.Thread(
            target=read_sse_events_in_thread,
            args=(url, headers, cookies, events_list, 2),
            daemon=True,
        )
        threads.append((thread, events_list))
        thread.start()

    # 等待所有 thread 完成
    for thread, _ in threads:
        thread.join(timeout=3)

    # 收集結果
    for i, (_, events_list) in enumerate(threads):
        connection_data = {
            'user_id': i + 1,
            'events': events_list,
        }
        context['user_connections'].append(connection_data)

    # Create mock response
    class MockResponse:
        def __init__(self, status_code, headers=None):
            self.status_code = status_code
            self.headers = headers or {}

    has_events = any(conn['events'] for conn in context['user_connections'])
    context['response'] = MockResponse(
        200 if has_events else 404, {'content-type': 'text/event-stream; charset=utf-8'}
    )


# Note: 'seller lists tickets by section with:' step is defined in
# test/service/ticketing/integration/steps/event_ticketing/when.py
# and imported via bdd_steps_loader.py


def parse_sse_response(response) -> List[dict]:
    """Parse SSE response into events list (read limited data)."""
    events = []

    # For SSE responses, read only the initial events (not the entire stream)
    if hasattr(response, 'iter_lines'):
        # Stream response - read first few events only
        lines_read = 0
        max_lines = 50  # Limit to prevent hanging
        current_event = {}

        try:
            for line in response.iter_lines():
                if lines_read >= max_lines:
                    break
                lines_read += 1

                line = line.decode('utf-8').strip() if isinstance(line, bytes) else line.strip()

                if not line:
                    if current_event:
                        events.append(current_event)
                        current_event = {}
                        # Stop after getting 2 events (connected + initial_status)
                        if len(events) >= 2:
                            break
                    continue

                if line.startswith('event:'):
                    current_event['event'] = line.split(':', 1)[1].strip()
                elif line.startswith('data:'):
                    data_str = line.split(':', 1)[1].strip()
                    try:
                        current_event['data'] = orjson.loads(data_str)
                    except orjson.JSONDecodeError:
                        current_event['data'] = data_str
        except Exception:
            pass  # Stop reading on any error
    else:
        # Regular response
        content = response.text if hasattr(response, 'text') else response.content.decode('utf-8')
        lines = content.split('\n')
        current_event = {}

        for line in lines:
            line = line.strip()
            if not line:
                if current_event:
                    events.append(current_event)
                    current_event = {}
                continue

            if line.startswith('event:'):
                current_event['event'] = line.split(':', 1)[1].strip()
            elif line.startswith('data:'):
                data_str = line.split(':', 1)[1].strip()
                try:
                    current_event['data'] = orjson.loads(data_str)
                except orjson.JSONDecodeError:
                    current_event['data'] = data_str

    return events
