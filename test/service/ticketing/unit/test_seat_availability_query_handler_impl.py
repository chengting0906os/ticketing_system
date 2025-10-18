"""
Unit tests for SeatAvailabilityQueryHandlerImpl

測試 ticketing service 的座位可用性查詢處理器
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.platform.exception.exceptions import NotFoundError
from src.service.ticketing.driven_adapter.state import seat_availability_query_handler_impl
from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
    SeatAvailabilityQueryHandlerImpl,
)

# Centralized mock target to avoid hardcoding throughout tests
KVROCKS_CLIENT_MOCK_TARGET = (
    f'{seat_availability_query_handler_impl.__name__}.kvrocks_client.get_client'
)


class TestMakeKey:
    """測試 _make_key() helper 函數"""

    def test_make_key_with_prefix(self):
        """測試：當有設定 KVROCKS_KEY_PREFIX 時，應該加上前綴"""
        with patch.dict(os.environ, {'KVROCKS_KEY_PREFIX': 'ticketing_system:state:'}):
            # Force reload to pick up new env var
            from importlib import reload

            import src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl as module

            reload(module)

            result = module._make_key('section_stats:1:A-1')
            assert result == 'ticketing_system:state:section_stats:1:A-1'

    def test_make_key_without_prefix(self):
        """測試：當沒有設定 KVROCKS_KEY_PREFIX 時，應該直接返回 key"""
        with patch.dict(os.environ, {'KVROCKS_KEY_PREFIX': ''}, clear=True):
            from importlib import reload

            import src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl as module

            reload(module)

            result = module._make_key('section_stats:1:A-1')
            assert result == 'section_stats:1:A-1'


class TestCheckSubsectionAvailability:
    """測試 check_subsection_availability() 方法"""

    @pytest.fixture
    def handler(self):
        return SeatAvailabilityQueryHandlerImpl()

    @pytest.fixture
    def mock_kvrocks_client(self):
        """Mock Kvrocks client"""
        client = MagicMock()
        client.hgetall = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_returns_true_when_sufficient_seats_available(self, handler, mock_kvrocks_client):
        """測試：當可用座位充足時，應該返回 True"""
        # Given: 50 seats available, need 10
        mock_stats = {
            'section_id': 'A-1',
            'event_id': '1',
            'available': '50',
            'reserved': '30',
            'sold': '20',
            'total': '100',
        }
        mock_kvrocks_client.hgetall.return_value = mock_stats

        # When
        with patch(
            KVROCKS_CLIENT_MOCK_TARGET,
            return_value=mock_kvrocks_client,
        ):
            result = await handler.check_subsection_availability(
                event_id=1, section='A', subsection=1, required_quantity=10
            )

        # Then
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient_seats(self, handler, mock_kvrocks_client):
        """測試：當可用座位不足時，應該返回 False"""
        # Given: Only 5 seats available, need 10
        mock_stats = {
            'available': '5',
            'reserved': '50',
            'sold': '45',
            'total': '100',
        }
        mock_kvrocks_client.hgetall.return_value = mock_stats

        # When
        with patch(
            KVROCKS_CLIENT_MOCK_TARGET,
            return_value=mock_kvrocks_client,
        ):
            result = await handler.check_subsection_availability(
                event_id=1, section='B', subsection=2, required_quantity=10
            )

        # Then
        assert result is False

    @pytest.mark.asyncio
    async def test_queries_correct_kvrocks_key(self, handler, mock_kvrocks_client):
        """測試：應該使用正確的 Kvrocks key 格式查詢"""
        # Given
        mock_stats = {'available': '10'}
        mock_kvrocks_client.hgetall.return_value = mock_stats

        # When
        with patch(
            KVROCKS_CLIENT_MOCK_TARGET,
            return_value=mock_kvrocks_client,
        ):
            await handler.check_subsection_availability(
                event_id=100, section='C', subsection=3, required_quantity=5
            )

        # Then: Should query with correct key format (with dynamic prefix)
        mock_kvrocks_client.hgetall.assert_called_once()
        actual_key = mock_kvrocks_client.hgetall.call_args[0][0]
        # Key should end with the pattern (prefix may vary by environment)
        assert actual_key.endswith('section_stats:100:C-3')

    @pytest.mark.asyncio
    async def test_raises_not_found_error_when_section_not_exists(
        self, handler, mock_kvrocks_client
    ):
        """測試：當 section 不存在時，應該拋出 NotFoundError"""
        # Given: Kvrocks returns empty dict
        mock_kvrocks_client.hgetall.return_value = {}

        # When/Then
        with patch(
            KVROCKS_CLIENT_MOCK_TARGET,
            return_value=mock_kvrocks_client,
        ):
            with pytest.raises(NotFoundError, match='Section Z-99 not found'):
                await handler.check_subsection_availability(
                    event_id=999, section='Z', subsection=99, required_quantity=1
                )

    @pytest.mark.asyncio
    async def test_handles_edge_case_exact_quantity_match(self, handler, mock_kvrocks_client):
        """測試：當可用座位數量剛好等於需求時，應該返回 True"""
        # Given: Exactly 10 seats available, need 10
        mock_stats = {'available': '10', 'total': '100'}
        mock_kvrocks_client.hgetall.return_value = mock_stats

        # When
        with patch(
            KVROCKS_CLIENT_MOCK_TARGET,
            return_value=mock_kvrocks_client,
        ):
            result = await handler.check_subsection_availability(
                event_id=1, section='A', subsection=1, required_quantity=10
            )

        # Then
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_available_count_as_string(self, handler, mock_kvrocks_client):
        """測試：應該正確處理 Kvrocks 返回的字符串類型數字"""
        # Given: Kvrocks returns strings (as it always does)
        mock_stats = {
            'available': '100',  # String type from Redis
        }
        mock_kvrocks_client.hgetall.return_value = mock_stats

        # When
        with patch(
            KVROCKS_CLIENT_MOCK_TARGET,
            return_value=mock_kvrocks_client,
        ):
            result = await handler.check_subsection_availability(
                event_id=1, section='A', subsection=1, required_quantity=50
            )

        # Then: Should correctly convert string to int and compare
        assert result is True
