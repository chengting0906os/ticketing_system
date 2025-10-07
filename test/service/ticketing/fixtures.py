import os
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.state.kvrocks_client import kvrocks_client_sync
from src.service.ticketing.driven_adapter.state.lua_script import INITIALIZE_SEATS_SCRIPT


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
    Auto-mock Kafka infrastructure to avoid starting real Kafka consumers in tests.

    Provides test-specific seat initialization logic (direct Kvrocks writes, bypassing async Kafka processing).

    Only enabled for feature tests and tests using 'client' fixture.
    """
    # Skip for lua_script tests (they don't need mocking)
    if 'lua_script_tests' in request.node.nodeid:
        yield
        return

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

    async def mock_seat_initialization(
        self, *, event_id: int, ticket_tuples: list, seating_config: dict
    ) -> None:
        """測試環境下的座位初始化：直接呼叫 Lua script（sync mode for test）"""

        # 獲取 key prefix
        _KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')

        # 生成所有座位數據（與 handler 相同邏輯）
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

        # 準備 Lua script 參數
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

        # 執行 Lua script (sync)
        client = kvrocks_client_sync.connect()
        success_count = client.eval(INITIALIZE_SEATS_SCRIPT, 0, *args)

        if not success_count or success_count != len(all_seats):
            raise Exception(
                f'Seat initialization failed: expected {len(all_seats)}, got {success_count}'
            )

    with (
        patch(
            'src.service.ticketing.app.command.create_event_and_tickets_use_case'
            '.CreateEventAndTicketsUseCase._setup_kafka_infrastructure'
        ) as mock_setup,
        patch(
            'src.service.ticketing.app.command.create_event_and_tickets_use_case'
            '.CreateEventAndTicketsUseCase._start_seat_reservation_consumer_and_initialize_seats',
            new=mock_seat_initialization,
        ),
        patch(
            'src.platform.message_queue.event_publisher.publish_domain_event',
            side_effect=mock_publish_domain_event,
        ),
        patch(
            'src.platform.message_queue.event_publisher._get_quix_app',
            side_effect=mock_get_quix_app,
        ),
    ):
        # 設置 mock 返回值為 AsyncMock
        mock_setup.return_value = AsyncMock()

        yield {'setup_kafka': mock_setup}
