from unittest.mock import patch

import pytest

# Patch paths - extracted to avoid hardcoding
PATCH_MQ_ORCHESTRATOR_SETUP = (
    'src.service.ticketing.driven_adapter.message_queue.mq_infra_orchestrator'
    '.MqInfraOrchestrator.setup_mq_infra'
)
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

    async def mock_setup_mq_infra(self, *, event_id: int, seating_config: dict) -> None:
        """Mock MQ setup - no-op in tests."""
        pass

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
        patch(PATCH_MQ_ORCHESTRATOR_SETUP, new=mock_setup_mq_infra),
        patch(PATCH_SEAT_INITIALIZER, new=mock_initialize_seats),
        patch(PATCH_EVENT_PUBLISHER, side_effect=mock_publish_domain_event),
        patch(PATCH_QUIX_APP, side_effect=mock_get_quix_app),
    ):
        yield {
            'mq_orchestrator': mock_setup_mq_infra,
            'seat_initializer': mock_initialize_seats,
        }
