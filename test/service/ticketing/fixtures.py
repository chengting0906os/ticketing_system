from collections import defaultdict
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
import multiprocessing
import os
import socket
import time
from typing import Any
from unittest.mock import patch

import httpx
import orjson
import pytest
import uvicorn

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    TicketStatus,
)
from src.service.ticketing.domain.entity.ticket_entity import TicketEntity
from test.kvrocks_test_client import kvrocks_test_client


# Patch paths - extracted to avoid hardcoding
PATCH_SEAT_INITIALIZER = (
    'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl'
    '.InitEventAndTicketsStateHandlerImpl.initialize_seats_from_config'
)
PATCH_EVENT_PUBLISHER = 'src.platform.message_queue.event_publisher.publish_domain_event'


@pytest.fixture
def context() -> dict[str, Any]:
    """Unified state fixture for all BDD tests."""
    return {}


@pytest.fixture
def available_tickets() -> list[TicketEntity]:
    """Sample available tickets for unit testing."""
    now = datetime.now()
    return [
        TicketEntity(
            id=1,
            event_id=1,
            section='A',
            subsection=1,
            row=1,
            seat=1,
            price=1000,
            status=TicketStatus.AVAILABLE,
            created_at=now,
            updated_at=now,
        )
    ]


@pytest.fixture(autouse=True, scope='function')
def mock_kafka_infrastructure(
    request: pytest.FixtureRequest,
) -> Generator[dict[str, Any], None, None]:
    """
    Auto-mock MQ infrastructure to avoid starting real Kafka consumers in tests.

    Skips unit tests (marked with @pytest.mark.unit).
    """
    if request.node.get_closest_marker('unit'):
        yield {}
        return

    async def mock_initialize_seats(
        self: object, *, event_id: int, seating_config: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Test implementation: Direct Kvrocks writes via Pipeline.
        Bypasses async Kafka processing for faster, deterministic tests.
        """

        # Get key prefix
        _KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')

        def _make_key(key: str) -> str:
            return f'{_KEY_PREFIX}{key}'

        # Generate seat data (same logic as real handler)
        # Compact format: rows/cols at top level, subsections as integer count
        all_seats = []
        rows = seating_config.get('rows', 10)
        cols = seating_config.get('cols', 10)

        for section in seating_config.get('sections', []):
            section_name = section['name']
            price = section['price']
            subsections_count = section.get('subsections', 1)

            for subsection_num in range(1, subsections_count + 1):
                for row in range(1, rows + 1):
                    for seat_num in range(1, cols + 1):
                        seat_index = (row - 1) * cols + (seat_num - 1)
                        all_seats.append(
                            {
                                'section': section_name,
                                'subsection': subsection_num,
                                'row': row,
                                'seat_num': seat_num,
                                'seat_index': seat_index,
                                'price': price,
                                'rows': rows,
                                'cols': cols,
                            }
                        )

        # Prepare section statistics and unified event config (JSON - hierarchical)
        section_stats = defaultdict(int)
        event_state = {'sections': {}}  # Unified JSON structure

        for seat in all_seats:
            section_id = f'{seat["section"]}-{seat["subsection"]}'
            section_stats[section_id] += 1

            # Build event_state JSON structure (hierarchical - price at section level)
            section_name = seat['section']  # e.g., "A"
            subsection_num = str(seat['subsection'])  # e.g., "1"

            # Create section if not exists (price stored at section level)
            if section_name not in event_state['sections']:
                event_state['sections'][section_name] = {
                    'price': seat['price'],  # ✨ Price at section level (not duplicated)
                    'subsections': {},
                }

            # Create subsection if not exists (stats stored at subsection level)
            if subsection_num not in event_state['sections'][section_name]['subsections']:
                event_state['sections'][section_name]['subsections'][subsection_num] = {
                    'rows': seat['rows'],
                    'cols': seat['cols'],
                    'stats': {  # ✨ Stats at subsection level
                        'available': 0,  # Will be set below
                        'reserved': 0,
                        'sold': 0,
                        'total': 0,  # Will be set below
                        'updated_at': 0,
                    },
                }

        # Use Pipeline to batch write all operations (sync version)
        client = kvrocks_test_client.connect()
        pipe = client.pipeline()
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        # Write seat bitfields (status only - prices moved to JSON)
        # 1-bit per seat: 0=available, 1=reserved
        for seat in all_seats:
            section_id = f'{seat["section"]}-{seat["subsection"]}'
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            # Set seat status to AVAILABLE (0)
            pipe.setbit(bf_key, seat['seat_index'], 0)

            # ✨ REMOVED: seat_meta Hash (prices now in JSON)

        # Update stats with actual counts (before writing JSON)
        for section_id, total_seats in section_stats.items():
            # Add section to event's section index
            pipe.zadd(_make_key(f'event_sections:{event_id}'), {section_id: 0})

            # ✨ Update stats in event_state JSON structure (navigate hierarchical structure)
            # Parse section_id (e.g., "A-1" -> section="A", subsection="1")
            parts = section_id.split('-')
            section_name = parts[0]
            subsection_num = parts[1]

            event_state['sections'][section_name]['subsections'][subsection_num]['stats'][
                'available'
            ] = total_seats
            event_state['sections'][section_name]['subsections'][subsection_num]['stats'][
                'total'
            ] = total_seats
            event_state['sections'][section_name]['subsections'][subsection_num]['stats'][
                'updated_at'
            ] = int(timestamp)

            # ✨ REMOVED: section_stats Hash (stats now in event_state JSON)
            # ✨ REMOVED: section_config Hash (config now in JSON)

        # Execute pipeline
        pipe.execute()

        # Write unified event config as JSON (single key per event)
        config_key = _make_key(f'event_state:{event_id}')
        event_state_json = orjson.dumps(event_state).decode()

        try:
            # Try JSON.SET first (Kvrocks native JSON support)
            client.execute_command('JSON.SET', config_key, '$', event_state_json)
        except Exception:
            # Fallback: Store as regular string if JSON commands not supported
            client.set(config_key, event_state_json)

        return {
            'success': True,
            'total_seats': len(all_seats),
            'sections_count': len(seating_config.get('sections', [])),
        }

    async def mock_publish_domain_event(*, event: object, topic: str, partition: int) -> bool:
        """Mock publishing domain events - bypasses Kafka completely"""
        return True

    with (
        patch(PATCH_SEAT_INITIALIZER, new=mock_initialize_seats),
        patch(PATCH_EVENT_PUBLISHER, side_effect=mock_publish_domain_event),
    ):
        yield {
            'seat_initializer': mock_initialize_seats,
        }


# =============================================================================
# SSE Test Fixtures (shared by event_ticketing and booking tests)
# =============================================================================


def get_free_port() -> int:
    """Get a free port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def run_server(port: int, env_vars: dict[str, str]) -> None:
    """Run uvicorn server in separate process with environment variables."""
    # Set environment variables in the spawned process
    for key, value in env_vars.items():
        os.environ[key] = value

    from test.test_main import app

    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')


@pytest.fixture(scope='function')
def http_server() -> Generator[str, None, None]:
    """Start a real HTTP server for SSE testing with dynamic port."""
    # Get a free port
    port = get_free_port()

    # Capture critical environment variables for the spawned process
    # Include all database and service configuration
    env_vars = {
        'KVROCKS_KEY_PREFIX': os.getenv('KVROCKS_KEY_PREFIX', 'test_'),
        'KVROCKS_HOST': os.getenv('KVROCKS_HOST', 'localhost'),
        'KVROCKS_PORT': os.getenv('KVROCKS_PORT', '6666'),
        'KVROCKS_DB': os.getenv('KVROCKS_DB', '0'),
        'POSTGRES_HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'POSTGRES_PORT': os.getenv('POSTGRES_PORT', '5432'),
        'POSTGRES_USER': os.getenv('POSTGRES_USER', 'postgres'),
        'POSTGRES_PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'POSTGRES_DB': os.getenv('POSTGRES_DB', 'ticketing_system_test_db'),
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
async def async_client(http_server: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for SSE testing."""
    async with httpx.AsyncClient(base_url=http_server, timeout=10.0) as client:
        yield client
