"""
Unit tests for SeatingConfigQueryHandlerImpl

Tests the seating config query handler with caching and TTL.
"""

import time
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from src.service.reservation.driven_adapter.state.seating_config_query_handler_impl import (
    CacheEntry,
    SeatingConfigQueryHandlerImpl,
)
from src.service.shared_kernel.domain.value_object.subsection_config import SubsectionConfig


class TestSeatingConfigQueryHandlerImpl:
    @pytest.fixture
    def handler(self) -> SeatingConfigQueryHandlerImpl:
        return SeatingConfigQueryHandlerImpl(ttl_seconds=10.0)

    @pytest.fixture
    def sample_seating_config(self) -> dict[str, Any]:
        return {
            'rows': 25,
            'cols': 20,
            'sections': [
                {'name': 'A', 'price': 3000, 'subsections': 10},
                {'name': 'B', 'price': 2000, 'subsections': 10},
            ],
        }

    # =========================================================================
    # _extract_section_config Tests
    # =========================================================================

    def test_extract_section_config_success(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """Test extracting config for existing section"""
        result = handler._extract_section_config(data=sample_seating_config, section='A')

        assert result == SubsectionConfig(rows=25, cols=20, price=3000)

    def test_extract_section_config_different_section(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """Test extracting config for section B"""
        result = handler._extract_section_config(data=sample_seating_config, section='B')

        assert result == SubsectionConfig(rows=25, cols=20, price=2000)

    def test_extract_section_config_missing_section(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """Test extracting config for non-existent section returns price=0"""
        result = handler._extract_section_config(data=sample_seating_config, section='Z')

        assert result == SubsectionConfig(rows=25, cols=20, price=0)

    def test_extract_section_config_empty_sections(
        self, handler: SeatingConfigQueryHandlerImpl
    ) -> None:
        """Test extracting config when sections array is empty"""
        data = {'rows': 10, 'cols': 5, 'sections': []}

        result = handler._extract_section_config(data=data, section='A')

        assert result == SubsectionConfig(rows=10, cols=5, price=0)

    # =========================================================================
    # _is_expired Tests
    # =========================================================================

    def test_is_expired_false_when_fresh(self, handler: SeatingConfigQueryHandlerImpl) -> None:
        """Test cache entry is not expired when fresh"""
        entry: CacheEntry = {'data': {}, 'timestamp': time.time()}

        assert handler._is_expired(entry=entry) is False

    def test_is_expired_true_when_old(self, handler: SeatingConfigQueryHandlerImpl) -> None:
        """Test cache entry is expired when older than TTL"""
        entry: CacheEntry = {'data': {}, 'timestamp': time.time() - 15.0}  # 15s ago, TTL is 10s

        assert handler._is_expired(entry=entry) is True

    def test_is_expired_just_under_ttl(self, handler: SeatingConfigQueryHandlerImpl) -> None:
        """Test cache entry just under TTL is not expired"""
        entry: CacheEntry = {'data': {}, 'timestamp': time.time() - 9.9}  # Just under 10s

        assert handler._is_expired(entry=entry) is False

    # =========================================================================
    # get_config Cache Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_config_returns_cached_value(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """Test get_config returns cached value without fetching"""
        # Pre-populate cache
        handler._cache[1] = {'data': sample_seating_config, 'timestamp': time.time()}

        result = await handler.get_config(event_id=1, section='A')

        assert result == SubsectionConfig(rows=25, cols=20, price=3000)

    @pytest.mark.asyncio
    async def test_get_config_different_sections_same_cache(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """Test multiple sections use same cached config"""
        handler._cache[1] = {'data': sample_seating_config, 'timestamp': time.time()}

        result_a = await handler.get_config(event_id=1, section='A')
        result_b = await handler.get_config(event_id=1, section='B')

        assert result_a.price == 3000
        assert result_b.price == 2000
        assert result_a.rows == result_b.rows == 25
        assert result_a.cols == result_b.cols == 20

    @pytest.mark.asyncio
    async def test_get_config_expired_cache_fetches_new(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """Test expired cache triggers new fetch"""
        # Pre-populate with expired cache
        handler._cache[1] = {'data': sample_seating_config, 'timestamp': time.time() - 15.0}

        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(
            return_value=['{"rows": 30, "cols": 25, "sections": [{"name": "A", "price": 5000}]}']
        )

        with patch(
            'src.service.reservation.driven_adapter.state.seating_config_query_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await handler.get_config(event_id=1, section='A')

        assert result == SubsectionConfig(rows=30, cols=25, price=5000)

    @pytest.mark.asyncio
    async def test_get_config_fetches_from_kvrocks(
        self, handler: SeatingConfigQueryHandlerImpl
    ) -> None:
        """Test get_config fetches from Kvrocks when cache empty"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(
            return_value=['{"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 3000}]}']
        )

        with patch(
            'src.service.reservation.driven_adapter.state.seating_config_query_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await handler.get_config(event_id=1, section='A')

        assert result == SubsectionConfig(rows=25, cols=20, price=3000)
        # Verify cache was populated
        assert 1 in handler._cache
        assert handler._cache[1]['data']['rows'] == 25

    @pytest.mark.asyncio
    async def test_get_config_raises_when_not_found(
        self, handler: SeatingConfigQueryHandlerImpl
    ) -> None:
        """Test get_config raises ValueError when config not found"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value=[None])

        with patch(
            'src.service.reservation.driven_adapter.state.seating_config_query_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            with pytest.raises(ValueError, match='No seating_config found for event 1'):
                await handler.get_config(event_id=1, section='A')

    # =========================================================================
    # Execution Order Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_cache_hit_skips_kvrocks_fetch(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """
        Test execution order on cache hit:
        1. Check cache → HIT
        2. Skip Kvrocks fetch
        3. Extract section config
        """
        call_order: list[str] = []

        # Pre-populate cache
        handler._cache[1] = {'data': sample_seating_config, 'timestamp': time.time()}

        # Wrap _extract_section_config to track calls
        original_extract = handler._extract_section_config

        def track_extract(*args: Any, **kwargs: Any) -> SubsectionConfig:
            call_order.append('extract_section_config')
            return original_extract(*args, **kwargs)

        handler._extract_section_config = track_extract

        with patch(
            'src.service.reservation.driven_adapter.state.seating_config_query_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = AsyncMock()

            result = await handler.get_config(event_id=1, section='A')

        # Kvrocks should NOT be called on cache hit
        mock_kvrocks.get_client.assert_not_called()
        assert call_order == ['extract_section_config']
        assert result.price == 3000

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_then_caches(
        self, handler: SeatingConfigQueryHandlerImpl
    ) -> None:
        """
        Test execution order on cache miss:
        1. Check cache → MISS
        2. Fetch from Kvrocks
        3. Cache result with timestamp
        4. Extract section config
        """
        call_order: list[str] = []

        mock_client = AsyncMock()

        async def track_kvrocks_fetch(*args: Any, **kwargs: Any) -> list[str]:
            call_order.append('kvrocks_fetch')
            return ['{"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 3000}]}']

        mock_client.execute_command = track_kvrocks_fetch

        # Wrap _extract_section_config
        original_extract = handler._extract_section_config

        def track_extract(*args: Any, **kwargs: Any) -> SubsectionConfig:
            call_order.append('extract_section_config')
            return original_extract(*args, **kwargs)

        handler._extract_section_config = track_extract

        with patch(
            'src.service.reservation.driven_adapter.state.seating_config_query_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await handler.get_config(event_id=1, section='A')

        # Verify order: fetch → cache → extract
        assert call_order == ['kvrocks_fetch', 'extract_section_config']
        assert 1 in handler._cache  # Cache was populated
        assert 'timestamp' in handler._cache[1]  # Timestamp was set
        assert result.price == 3000

    @pytest.mark.asyncio
    async def test_expired_cache_refetches_from_kvrocks(
        self, handler: SeatingConfigQueryHandlerImpl, sample_seating_config: dict[str, Any]
    ) -> None:
        """
        Test execution order on expired cache:
        1. Check cache → HIT but EXPIRED
        2. Fetch from Kvrocks (new data)
        3. Update cache with new timestamp
        4. Extract section config
        """
        call_order: list[str] = []

        # Pre-populate with expired cache (old data)
        old_timestamp = time.time() - 15.0
        handler._cache[1] = {'data': sample_seating_config, 'timestamp': old_timestamp}

        mock_client = AsyncMock()

        async def track_kvrocks_fetch(*args: Any, **kwargs: Any) -> list[str]:
            call_order.append('kvrocks_fetch')
            # Return NEW data with different price
            return ['{"rows": 30, "cols": 25, "sections": [{"name": "A", "price": 5000}]}']

        mock_client.execute_command = track_kvrocks_fetch

        with patch(
            'src.service.reservation.driven_adapter.state.seating_config_query_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await handler.get_config(event_id=1, section='A')

        # Verify Kvrocks was called (expired cache)
        assert call_order == ['kvrocks_fetch']
        # Verify cache was updated with new data
        updated_entry = cast(CacheEntry, handler._cache[1])
        assert updated_entry['data']['rows'] == 30
        assert updated_entry['timestamp'] > old_timestamp
        # Verify new data is returned
        assert result == SubsectionConfig(rows=30, cols=25, price=5000)
