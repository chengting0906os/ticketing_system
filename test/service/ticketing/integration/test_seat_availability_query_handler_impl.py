"""
Integration tests for SeatAvailabilityQueryHandlerImpl

測試 ticketing service 與 Kvrocks 的整合行為
"""

import os

import pytest

from src.platform.exception.exceptions import NotFoundError
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
    SeatAvailabilityQueryHandlerImpl,
    _make_key,
)


class TestMakeKeyIntegration:
    """測試 _make_key() 在實際環境中的行為"""

    def test_make_key_uses_environment_prefix(self):
        """測試：應該使用環境變數中的 prefix"""
        # Given: conftest.py 會設定 KVROCKS_KEY_PREFIX
        prefix = os.getenv('KVROCKS_KEY_PREFIX', '')

        # When
        result = _make_key('section_stats:1:A-1')

        # Then
        if prefix:
            assert result == f'{prefix}section_stats:1:A-1'
        else:
            assert result == 'section_stats:1:A-1'


class TestCheckSubsectionAvailabilityIntegration:
    """測試 check_subsection_availability() 與真實 Kvrocks 的整合"""

    @pytest.fixture
    async def handler(self):
        await kvrocks_client.initialize()
        return SeatAvailabilityQueryHandlerImpl()

    @pytest.mark.asyncio
    async def test_returns_true_when_sufficient_seats_available(self, handler):
        """測試：當可用座位充足時，應該返回 True"""
        # Given: 在 Kvrocks 中設定座位統計
        client = kvrocks_client.get_client()
        key = _make_key('section_stats:1:A-1')
        await client.hset(  # type: ignore
            key,
            mapping={
                'section_id': 'A-1',
                'event_id': '1',
                'available': '50',
                'reserved': '30',
                'sold': '20',
                'total': '100',
            },
        )

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='A', subsection=1, required_quantity=10
        )

        # Then
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient_seats(self, handler):
        """測試：當可用座位不足時，應該返回 False"""
        # Given: 只有 5 個可用座位
        client = kvrocks_client.get_client()
        key = _make_key('section_stats:1:B-2')
        await client.hset(  # type: ignore
            key,
            mapping={
                'available': '5',
                'reserved': '50',
                'sold': '45',
                'total': '100',
            },
        )

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='B', subsection=2, required_quantity=10
        )

        # Then
        assert result is False

    @pytest.mark.asyncio
    async def test_queries_correct_kvrocks_key(self, handler):
        """測試：應該使用正確的 Kvrocks key 格式查詢"""
        # Given
        client = kvrocks_client.get_client()
        key = _make_key('section_stats:100:C-3')
        await client.hset(key, mapping={'available': '10'})  # type: ignore

        # When
        result = await handler.check_subsection_availability(
            event_id=100, section='C', subsection=3, required_quantity=5
        )

        # Then: 應該能夠讀取到資料並返回正確結果
        assert result is True

        # Verify the key was actually used
        stored_data = await client.hgetall(key)  # type: ignore
        assert stored_data['available'] == '10'  # type: ignore

    @pytest.mark.asyncio
    async def test_raises_not_found_error_when_section_not_exists(self, handler):
        """測試：當 section 不存在時，應該拋出 NotFoundError"""
        # Given: Kvrocks 中沒有這個 section 的資料（conftest 會清理）

        # When/Then
        with pytest.raises(NotFoundError, match='Section Z-99 not found'):
            await handler.check_subsection_availability(
                event_id=999, section='Z', subsection=99, required_quantity=1
            )

    @pytest.mark.asyncio
    async def test_handles_edge_case_exact_quantity_match(self, handler):
        """測試：當可用座位數量剛好等於需求時，應該返回 True"""
        # Given: 剛好 10 個座位
        client = kvrocks_client.get_client()
        key = _make_key('section_stats:1:A-1')
        await client.hset(key, mapping={'available': '10', 'total': '100'})  # type: ignore

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='A', subsection=1, required_quantity=10
        )

        # Then
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_available_count_as_string(self, handler):
        """測試：應該正確處理 Kvrocks 返回的字符串類型數字"""
        # Given: Kvrocks 總是返回字串
        client = kvrocks_client.get_client()
        key = _make_key('section_stats:1:A-1')
        await client.hset(key, mapping={'available': '100'})  # type: ignore

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='A', subsection=1, required_quantity=50
        )

        # Then: 應該正確轉換字串為整數並比較
        assert result is True
