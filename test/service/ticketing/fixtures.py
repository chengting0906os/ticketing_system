from collections import defaultdict
from collections.abc import Generator
from datetime import datetime, timezone
import os
from typing import Any
from unittest.mock import patch

import orjson
import pytest

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    Ticket,
    TicketStatus,
)
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
def available_tickets() -> list[Ticket]:
    """Sample available tickets for unit testing."""
    now = datetime.now()
    return [
        Ticket(
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
        for seat in all_seats:
            section_id = f'{seat["section"]}-{seat["subsection"]}'
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            offset = seat['seat_index'] * 2

            # Set seat status to AVAILABLE (00)
            pipe.setbit(bf_key, offset, 0)
            pipe.setbit(bf_key, offset + 1, 0)

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
