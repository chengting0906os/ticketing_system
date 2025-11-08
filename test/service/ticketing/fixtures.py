from unittest.mock import patch

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

        # Prepare section statistics and configurations
        section_stats = defaultdict(int)
        section_configs = {}

        for seat in all_seats:
            section_id = f'{seat["section"]}-{seat["subsection"]}'
            section_stats[section_id] += 1

            if section_id not in section_configs:
                section_configs[section_id] = {
                    'rows': seat['rows'],
                    'seats_per_row': seat['seats_per_row'],
                }

        # Use Pipeline to batch write all operations (sync version)
        client = kvrocks_test_client.connect()
        pipe = client.pipeline()
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        # Write all seat bitfields and metadata
        for seat in all_seats:
            section_id = f'{seat["section"]}-{seat["subsection"]}'
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{seat["row"]}')
            offset = seat['seat_index'] * 2

            # Set seat status to AVAILABLE (00)
            pipe.setbit(bf_key, offset, 0)
            pipe.setbit(bf_key, offset + 1, 0)

            # Store seat metadata (price)
            pipe.hset(meta_key, str(seat['seat_num']), str(seat['price']))

        # Create section indexes and statistics
        for section_id, total_seats in section_stats.items():
            # Add section to event's section index
            pipe.zadd(_make_key(f'event_sections:{event_id}'), {section_id: 0})

            # Initialize section statistics
            stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
            pipe.hset(
                stats_key,
                mapping={
                    'section_id': section_id,
                    'event_id': str(event_id),
                    'available': str(total_seats),
                    'reserved': '0',
                    'sold': '0',
                    'total': str(total_seats),
                    'updated_at': timestamp,
                },
            )

            # Store section configuration
            config = section_configs[section_id]
            config_key = _make_key(f'section_config:{event_id}:{section_id}')
            pipe.hset(
                config_key,
                mapping={
                    'rows': str(config['rows']),
                    'seats_per_row': str(config['seats_per_row']),
                },
            )

        # Execute pipeline
        pipe.execute()

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
