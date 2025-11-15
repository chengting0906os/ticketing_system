from unittest.mock import patch

import orjson
import pytest


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
    Skips unit tests in test/service/*/unit/ directories.
    """
    # Skip for unit tests - they should test implementation directly
    if '/unit/' in str(request.fspath):
        yield
        return

    async def mock_initialize_seats(self, *, event_id: int, seating_config: dict) -> dict:
        """
        Test implementation: Direct Kvrocks writes via Pipeline.
        Bypasses async Kafka processing for faster, deterministic tests.
        """
        from collections import defaultdict
        from datetime import datetime, timezone
        import os

        from test.kvrocks_test_client import kvrocks_test_client

        # Get key prefix
        _KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')

        def _make_key(key: str) -> str:
            return f'{_KEY_PREFIX}{key}'

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
                                'rows': rows,
                                'seats_per_row': seats_per_row,
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
                    'seats_per_row': seat['seats_per_row'],
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
