import multiprocessing
import os
import socket
import time
from unittest.mock import patch

import httpx
import pytest
import uvicorn


# Patch paths - extracted to avoid hardcoding
PATCH_SEAT_INITIALIZER = (
    'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl'
    '.InitEventAndTicketsStateHandlerImpl.initialize_seats_from_config'
)
PATCH_EVENT_PUBLISHER = 'src.platform.message_queue.event_publisher.publish_domain_event'
PATCH_QUIX_APP = 'src.platform.message_queue.event_publisher._get_quix_app'


@pytest.fixture
def user_state():
    return {'request_data': {}, 'response': None}


@pytest.fixture
def event_state():
    return {}


@pytest.fixture
def booking_state():
    return {}


@pytest.fixture
def context():
    return {}


@pytest.fixture
def reservation_state():
    class ReservationState:
        pass

    return ReservationState()


@pytest.fixture(autouse=True, scope='function')
def mock_kafka_infrastructure(request):
    """
    Auto-mock MQ infrastructure to avoid starting real Kafka consumers in tests.

    Mocks the IMqInfraOrchestrator interface instead of implementation details.
    This follows clean architecture - tests depend on abstractions.

    Only enabled for feature tests and tests using 'client' fixture.
    """
    # Skip for lua_script tests (they don't need mocking)
    if 'lua_script_tests' in request.node.nodeid:
        yield
        return

    async def mock_initialize_seats(self, *, event_id: int, seating_config: dict) -> dict:
        """
        Test implementation: Direct Kvrocks writes via Lua script.
        Bypasses async Kafka processing for faster, deterministic tests.
        """
        import os

        from src.platform.state.kvrocks_client import kvrocks_client_sync
        from src.service.ticketing.driven_adapter.state.lua_script import INITIALIZE_SEATS_SCRIPT

        # Get key prefix
        _KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')

        # Generate seat data (same logic as real handler)
        all_seats = []
        for section in seating_config.get('sections', []):
            section_name = section['name']
            price = section['price']
            for subsection in section.get('subsections', []):
                subsection_num = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                for row in range(1, rows + 1):
                    for seat_num in range(1, seats_per_row + 1):
                        seat_index = (row - 1) * seats_per_row + (seat_num - 1)
                        all_seats.append(
                            {
                                'section': section_name,
                                'subsection': subsection_num,
                                'row': row,
                                'seat_num': seat_num,
                                'seat_index': seat_index,
                                'price': price,
                            }
                        )

        # Prepare Lua script args
        args = [_KEY_PREFIX, str(event_id)]
        for seat in all_seats:
            args.extend(
                [
                    seat['section'],
                    str(seat['subsection']),
                    str(seat['row']),
                    str(seat['seat_num']),
                    str(seat['seat_index']),
                    str(seat['price']),
                ]
            )

        # Execute Lua script (sync)
        client = kvrocks_client_sync.connect()
        success_count = client.eval(INITIALIZE_SEATS_SCRIPT, 0, *args)

        if not success_count or success_count != len(all_seats):
            raise Exception(
                f'Seat initialization failed: expected {len(all_seats)}, got {success_count}'
            )

        return {
            'success': True,
            'total_seats': len(all_seats),
            'sections_count': len(seating_config.get('sections', [])),
        }

    async def mock_publish_domain_event(event, topic: str, partition_key: str):
        """Mock publishing domain events - bypasses Kafka completely"""
        return True

    def mock_get_quix_app():
        """Mock Quix Application - returns a mock app that doesn't connect to Kafka"""
        from unittest.mock import MagicMock

        mock_app = MagicMock()
        mock_topic = MagicMock()
        mock_topic.name = 'mock_topic'
        mock_app.topic.return_value = mock_topic
        return mock_app

    with (
        patch(PATCH_SEAT_INITIALIZER, new=mock_initialize_seats),
        patch(PATCH_EVENT_PUBLISHER, side_effect=mock_publish_domain_event),
        patch(PATCH_QUIX_APP, side_effect=mock_get_quix_app),
    ):
        yield {
            'seat_initializer': mock_initialize_seats,
        }


# ============================================================================
# Seat Reservation SSE Testing Fixtures
# ============================================================================


def get_free_port():
    """Get a free port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def run_server(port: int, env_vars: dict):
    """Run uvicorn server in separate process with environment variables."""
    # Set environment variables in the spawned process
    for key, value in env_vars.items():
        os.environ[key] = value

    from test.test_main import app

    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')


@pytest.fixture(scope='function')
def http_server():
    """Start a real HTTP server for SSE testing with dynamic port."""
    # Get a free port
    port = get_free_port()

    # Capture critical environment variables for the spawned process
    env_vars = {
        'KVROCKS_KEY_PREFIX': os.getenv('KVROCKS_KEY_PREFIX', 'test_'),
        'KVROCKS_HOST': os.getenv('KVROCKS_HOST', 'localhost'),
        'KVROCKS_PORT': os.getenv('KVROCKS_PORT', '6666'),
        'KVROCKS_DB': os.getenv('KVROCKS_DB', '0'),
    }

    # Use spawn instead of fork to avoid issues in multi-threaded environments (CI)
    ctx = multiprocessing.get_context('spawn')
    server_process = ctx.Process(target=run_server, args=(port, env_vars), daemon=True)
    server_process.start()

    # Wait for server to be ready with health check
    base_url = f'http://127.0.0.1:{port}'
    max_retries = 30  # 30 seconds max wait
    for i in range(max_retries):
        try:
            response = httpx.get(f'{base_url}/health', timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            if i == max_retries - 1:
                # Last attempt failed, still yield the URL
                # (tests will fail with clear error if server didn't start)
                break
            time.sleep(1)

    yield base_url

    # Cleanup
    server_process.terminate()
    server_process.join(timeout=5)


@pytest.fixture
async def async_client(http_server):
    """Async HTTP client for SSE testing."""
    async with httpx.AsyncClient(base_url=http_server, timeout=10.0) as client:
        yield client
