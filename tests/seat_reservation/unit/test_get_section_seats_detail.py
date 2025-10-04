"""
Tests for get_section_seats_detail functionality
測試 GETRANGE 快速讀取座位狀態的功能
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.platform.state.redis_client import KvrocksStatsClient


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetSectionSeatsDetail:
    """測試 get_section_seats_detail 方法"""

    @pytest.fixture
    def kvrocks_client(self):
        """建立 KvrocksStatsClient 實例"""
        return KvrocksStatsClient()

    @pytest.fixture
    def mock_redis_client(self):
        """建立 mock Redis client"""
        client = AsyncMock()
        return client

    async def test_get_section_seats_detail_returns_500_seats(
        self, kvrocks_client, mock_redis_client, monkeypatch
    ):
        """測試：應該返回 500 個座位資料"""
        # Arrange
        event_id = 1
        section = 'A'
        subsection = 1

        # Mock async Redis methods (exists returns count of existing keys, not boolean)
        mock_redis_client.exists = AsyncMock(return_value=1)

        # Mock bitfield data: 125 bytes for 500 seats (2 bits each)
        # 第一個 byte = 0b00110000 (available, unavailable, available, available)
        bitfield_data = chr(0b00110000) + chr(0) * 124  # 1 byte with data + 124 zero bytes
        mock_redis_client.getrange = AsyncMock(return_value=bitfield_data)

        # Mock pipeline for price data
        mock_pipeline = MagicMock()
        mock_pipeline.hgetall = MagicMock()

        # Execute returns list of prices for each row (25 rows, 20 seats each)
        price_data = [{str(i): 3000 for i in range(1, 21)} for _ in range(25)]
        mock_pipeline.execute = AsyncMock(return_value=price_data)

        mock_redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        # Mock kvrocks_client.connect() - must be an AsyncMock that returns the client
        async_connect_mock = AsyncMock(return_value=mock_redis_client)
        monkeypatch.setattr(
            'src.platform.state.redis_client.kvrocks_client.connect', async_connect_mock
        )

        # Act
        result = await kvrocks_client.get_section_seats_detail(
            event_id=event_id, section=section, subsection=subsection, max_rows=25, seats_per_row=20
        )

        # Assert
        assert len(result) == 500, 'Should return 500 seats'
        assert result[0]['seat_id'] == 'A-1-1-1'
        assert result[0]['status'] == 'available'
        assert result[0]['price'] == 3000
        assert result[499]['seat_id'] == 'A-1-25-20'

    async def test_get_section_seats_detail_handles_partial_bitfield(
        self, kvrocks_client, mock_redis_client, monkeypatch
    ):
        """測試：應該正確處理部分初始化的 bitfield (補0)"""
        # Arrange
        event_id = 1
        section = 'B'
        subsection = 2

        # Mock async Redis methods (exists returns count of existing keys, not boolean)
        mock_redis_client.exists = AsyncMock(return_value=1)

        # Only 1 byte of data (4 seats initialized), rest should be padded with 0
        bitfield_data = chr(0b11010010)  # unavailable, reserved, available, sold
        mock_redis_client.getrange = AsyncMock(return_value=bitfield_data)

        # Mock pipeline for price data
        mock_pipeline = MagicMock()
        mock_pipeline.hgetall = MagicMock()

        # Execute returns list of prices for each row
        price_data = [{str(i): 2500 for i in range(1, 21)} for _ in range(25)]
        mock_pipeline.execute = AsyncMock(return_value=price_data)

        mock_redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        async_connect_mock = AsyncMock(return_value=mock_redis_client)
        monkeypatch.setattr(
            'src.platform.state.redis_client.kvrocks_client.connect', async_connect_mock
        )

        # Act
        result = await kvrocks_client.get_section_seats_detail(
            event_id=event_id, section=section, subsection=subsection, max_rows=25, seats_per_row=20
        )

        # Assert
        assert len(result) == 500, 'Should return 500 seats even with partial data'
        # First 4 seats from bitfield
        assert result[0]['status'] == 'unavailable'  # 0b11
        assert result[1]['status'] == 'reserved'  # 0b01
        assert result[2]['status'] == 'available'  # 0b00
        assert result[3]['status'] == 'sold'  # 0b10
        # Remaining seats should be 'available' (0b00 from padding)
        assert result[4]['status'] == 'available'
        assert result[499]['status'] == 'available'

    async def test_get_section_seats_detail_returns_empty_when_bitfield_not_found(
        self, kvrocks_client, mock_redis_client, monkeypatch
    ):
        """測試：當 bitfield 未初始化時應返回空陣列"""
        # Arrange
        event_id = 999
        section = 'Z'
        subsection = 99

        # Mock bitfield doesn't exist (exists returns 0 when key not found)
        mock_redis_client.exists = AsyncMock(return_value=0)

        async_connect_mock = AsyncMock(return_value=mock_redis_client)
        monkeypatch.setattr(
            'src.platform.state.redis_client.kvrocks_client.connect', async_connect_mock
        )

        # Act
        result = await kvrocks_client.get_section_seats_detail(
            event_id=event_id, section=section, subsection=subsection, max_rows=25, seats_per_row=20
        )

        # Assert
        assert result == [], 'Should return empty list when bitfield not initialized'
        # GETRANGE should not be called if bitfield doesn't exist
        mock_redis_client.getrange.assert_not_called()
