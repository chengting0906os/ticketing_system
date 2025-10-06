import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.state.kvrocks_client import kvrocks_client_sync


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


@pytest.fixture(autouse=True)
def mock_kafka_infrastructure():
    """
    自動 mock Kafka infrastructure 以避免在測試中啟動真實的 Kafka consumers

    同時提供測試環境下的座位初始化邏輯（直接寫入 Kvrocks，跳過 Kafka 異步處理）
    """

    async def mock_publish_domain_event(event, topic: str, partition_key: str):
        return True

    async def mock_seat_initialization(
        self, *, event_id: int, ticket_tuples: list, seating_config: dict
    ) -> None:
        """測試環境下的座位初始化：直接同步寫入 Kvrocks + 更新 event status"""

        # 1. 保存 section 配置到 Redis (新增)
        for section in seating_config.get('sections', []):
            section_name = section['name']
            for subsection in section.get('subsections', []):
                subsection_num = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']
                section_id = f'{section_name}-{subsection_num}'
                config_key = f'section_config:{event_id}:{section_id}'

                client = kvrocks_client_sync.connect()
                client.hset(
                    config_key, mapping={'rows': str(rows), 'seats_per_row': str(seats_per_row)}
                )

        # 2. 寫入 subsection_total metadata
        subsection_counts = {}
        for ticket_tuple in ticket_tuples:
            _, section, subsection, _, _, _, _ = ticket_tuple
            section_id = f'{section}-{subsection}'
            subsection_counts[section_id] = subsection_counts.get(section_id, 0) + 1

        client = kvrocks_client_sync.connect()
        for section_id, count in subsection_counts.items():
            # 寫入 total 和available counter
            total_key = f'subsection_total:{event_id}:{section_id}'
            avail_key = f'subsection_avail:{event_id}:{section_id}'
            client.set(total_key, count)
            client.set(avail_key, count)  # 初始時全部可用

            # 創建空的 bitfield (表示已初始化，所有座位預設為 available=0b00)
            bf_key = f'seats_bf:{event_id}:{section_id}'
            client.set(bf_key, b'\x00')  # 設置一個初始byte表示已初始化

        # 3. 直接初始化座位狀態到 Kvrocks（跳過 Kafka）

        # 收集每個 row 的價格資訊
        seat_meta_data = {}  # {(event_id, section_id, row): {seat_num: price}}
        section_seat_counts = {}  # 統計每個 section 的座位數

        for ticket_tuple in ticket_tuples:
            _, section, subsection, row, seat, price, status = ticket_tuple
            seat_id = f'{section}-{subsection}-{row}-{seat}'
            section_id = f'{section}-{subsection}'
            key = f'seat:{seat_id}'

            seat_state = {
                'status': 'AVAILABLE',
                'event_id': event_id,
                'price': price,
                'initialized_at': int(time.time()),
            }

            client.set(key, json.dumps(seat_state))

            # 收集 seat_meta 資料
            meta_key = (event_id, section_id, row)
            if meta_key not in seat_meta_data:
                seat_meta_data[meta_key] = {}
            seat_meta_data[meta_key][str(seat)] = price

            # 統計座位數
            section_seat_counts[section_id] = section_seat_counts.get(section_id, 0) + 1

        # 寫入 seat_meta Hash
        for (event_id, section_id, row), prices in seat_meta_data.items():
            meta_key = f'seat_meta:{event_id}:{section_id}:{row}'
            client.hset(meta_key, mapping=prices)

        # 4. 建立 event_sections 索引和 section_stats 統計
        timestamp = int(time.time())
        for section_id, count in section_seat_counts.items():
            # 建立索引 (使用 sorted set，score 為 0)
            client.zadd(f'event_sections:{event_id}', {section_id: 0})

            # 設置統計 (初始狀態：所有座位都是 AVAILABLE)
            stats_key = f'section_stats:{event_id}:{section_id}'
            client.hset(
                stats_key,
                mapping={
                    'section_id': section_id,
                    'event_id': str(event_id),
                    'available': str(count),
                    'reserved': '0',
                    'sold': '0',
                    'total': str(count),
                    'updated_at': str(timestamp),
                },
            )

        # Note: Event status update is handled by the use case, not here

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
    ):
        # 設置 mock 返回值為 AsyncMock
        mock_setup.return_value = AsyncMock()

        yield {'setup_kafka': mock_setup}
