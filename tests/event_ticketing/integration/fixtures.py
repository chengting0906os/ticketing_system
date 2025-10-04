import json
import os
import time
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.platform.state.redis_client import kvrocks_client_sync


@pytest.fixture
def event_state():
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

    async def mock_seat_initialization(self, *, event_id: int, ticket_tuples: list) -> None:
        """測試環境下的座位初始化：直接同步寫入 Kvrocks + 更新 event status"""

        # 1. 寫入 subsection_total metadata
        subsection_counts = {}
        for ticket_tuple in ticket_tuples:
            _, section, subsection, _, _, _, _ = ticket_tuple
            section_id = f'{section}-{subsection}'
            subsection_counts[section_id] = subsection_counts.get(section_id, 0) + 1

        client = kvrocks_client_sync.connect()
        for section_id, count in subsection_counts.items():
            # 寫入 total 和 available counter
            total_key = f'subsection_total:{event_id}:{section_id}'
            avail_key = f'subsection_avail:{event_id}:{section_id}'
            client.set(total_key, count)
            client.set(avail_key, count)  # 初始時全部可用

            # 初始化 bitfield (用於檢查 section 是否已初始化)
            bf_key = f'seats_bf:{event_id}:{section_id}'
            client.set(bf_key, '0')  # 設置一個初始值表示已初始化

        # 2. 直接初始化座位狀態到 Kvrocks（跳過 Kafka）

        for ticket_tuple in ticket_tuples:
            _, section, subsection, row, seat, price, status = ticket_tuple
            seat_id = f'{section}-{subsection}-{row}-{seat}'
            key = f'seat:{seat_id}'

            seat_state = {
                'status': 'AVAILABLE',
                'event_id': event_id,
                'price': price,
                'initialized_at': int(time.time()),
            }

            client.set(key, json.dumps(seat_state))

        # 3. 更新 event status 從 DRAFT 到 AVAILABLE (模擬真實流程)

        DB_CONFIG = {
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD'),
            'host': os.getenv('POSTGRES_SERVER'),
            'port': os.getenv('POSTGRES_PORT'),
            'test_db': os.environ.get(
                'POSTGRES_DB', 'ticketing_system_test_db'
            ),  # Use worker-specific DB
        }
        TEST_DATABASE_URL = f'postgresql+asyncpg://{DB_CONFIG["user"]}:{DB_CONFIG["password"]}@{DB_CONFIG["host"]}:{DB_CONFIG["port"]}/{DB_CONFIG["test_db"]}'

        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE event SET status = 'available' WHERE id = :event_id"),
                {'event_id': event_id},
            )
        await engine.dispose()

    with (
        patch(
            'src.event_ticketing.app.command.create_event_use_case'
            '.CreateEventUseCase._setup_kafka_infrastructure'
        ) as mock_setup,
        patch(
            'src.event_ticketing.app.command.create_event_use_case'
            '.CreateEventUseCase._start_seat_reservation_consumer_and_initialize_seats',
            new=mock_seat_initialization,
        ),
    ):
        # 設置 mock 返回值為 AsyncMock
        mock_setup.return_value = AsyncMock()

        yield {'setup_kafka': mock_setup}
