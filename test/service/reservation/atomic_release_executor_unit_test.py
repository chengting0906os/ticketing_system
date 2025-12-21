"""
Unit tests for AtomicReleaseExecutor

Tests:
- Idempotency: Already released booking returns cached result
- Successful release updates booking metadata to RELEASE_SUCCESS
- Release updates event stats (available +N, reserved -N)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor import (
    AtomicReleaseExecutor,
)


class TestAtomicReleaseIdempotency:
    """Test idempotency via booking metadata check."""

    @pytest.fixture
    def mock_booking_metadata_handler(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def executor(self, mock_booking_metadata_handler: AsyncMock) -> AtomicReleaseExecutor:
        return AtomicReleaseExecutor(booking_metadata_handler=mock_booking_metadata_handler)

    @pytest.mark.asyncio
    async def test_already_released_booking_returns_success_without_action(
        self,
        executor: AtomicReleaseExecutor,
        mock_booking_metadata_handler: AsyncMock,
    ) -> None:
        """
        Test that already released booking returns success immediately.
        No Kvrocks operations should be performed.
        """
        # Arrange - booking already has RELEASE_SUCCESS status
        mock_booking_metadata_handler.get_booking_metadata.return_value = {
            'status': 'RELEASE_SUCCESS',
            'released_seats': '["1-1", "1-2"]',
        }

        # Act
        result = await executor.execute_atomic_release(
            booking_id='test-booking-id',
            event_id=1,
            section='A',
            subsection=1,
            seat_positions=['1-1', '1-2'],
        )

        # Assert - all seats should be marked as successful (idempotent)
        assert result == {'1-1': True, '1-2': True}
        # Verify no Kvrocks operations were performed (only metadata check)
        mock_booking_metadata_handler.get_booking_metadata.assert_called_once_with(
            booking_id='test-booking-id'
        )

    @pytest.mark.asyncio
    async def test_pending_reservation_proceeds_with_release(
        self,
        executor: AtomicReleaseExecutor,
        mock_booking_metadata_handler: AsyncMock,
    ) -> None:
        """
        Test that booking with RESERVE_SUCCESS status proceeds with release.
        """
        # Arrange - booking has RESERVE_SUCCESS status (not yet released)
        mock_booking_metadata_handler.get_booking_metadata.return_value = {
            'status': 'RESERVE_SUCCESS',
            'reserved_seats': '["1-1", "1-2"]',
        }

        # Mock Kvrocks client
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value=b'[20]')  # cols = 20
        mock_pipe = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.hset = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[])
        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        with patch(
            'src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            # Act
            result = await executor.execute_atomic_release(
                booking_id='test-booking-id',
                event_id=1,
                section='A',
                subsection=1,
                seat_positions=['1-1', '1-2'],
            )

            # Assert - all seats should be released
            assert result == {'1-1': True, '1-2': True}
            # Verify pipeline was executed
            mock_pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_metadata_proceeds_with_release(
        self,
        executor: AtomicReleaseExecutor,
        mock_booking_metadata_handler: AsyncMock,
    ) -> None:
        """
        Test that missing metadata still proceeds with release.
        (Edge case - metadata might be cleaned up already)
        """
        # Arrange - no metadata found
        mock_booking_metadata_handler.get_booking_metadata.return_value = None

        # Mock Kvrocks client
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value=b'[20]')
        mock_pipe = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.hset = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[])
        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        with patch(
            'src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            # Act
            result = await executor.execute_atomic_release(
                booking_id='test-booking-id',
                event_id=1,
                section='A',
                subsection=1,
                seat_positions=['1-1', '1-2'],
            )

            # Assert - should still succeed
            assert result == {'1-1': True, '1-2': True}


class TestAtomicReleaseMetadataUpdate:
    """Test that release updates booking metadata to RELEASE_SUCCESS."""

    @pytest.fixture
    def mock_booking_metadata_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.get_booking_metadata.return_value = {
            'status': 'RESERVE_SUCCESS',
        }
        return handler

    @pytest.fixture
    def executor(self, mock_booking_metadata_handler: AsyncMock) -> AtomicReleaseExecutor:
        return AtomicReleaseExecutor(booking_metadata_handler=mock_booking_metadata_handler)

    @pytest.mark.asyncio
    async def test_release_updates_metadata_to_release_success(
        self,
        executor: AtomicReleaseExecutor,
    ) -> None:
        """
        Test that successful release updates booking metadata to RELEASE_SUCCESS.
        """
        # Mock Kvrocks client
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value=b'[20]')
        mock_pipe = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.hset = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[])
        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        with patch(
            'src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            # Act
            await executor.execute_atomic_release(
                booking_id='test-booking-id',
                event_id=1,
                section='A',
                subsection=1,
                seat_positions=['1-1', '1-2'],
            )

            # Assert - hset should be called with RELEASE_SUCCESS status
            mock_pipe.hset.assert_called_once()
            call_args = mock_pipe.hset.call_args
            assert call_args[1]['mapping']['status'] == 'RELEASE_SUCCESS'
            # orjson doesn't add spaces after commas
            assert '1-1' in call_args[1]['mapping']['released_seats']
            assert '1-2' in call_args[1]['mapping']['released_seats']


class TestAtomicReleaseConfigNotFound:
    """Test handling when event config is not found."""

    @pytest.fixture
    def mock_booking_metadata_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.get_booking_metadata.return_value = {'status': 'RESERVE_SUCCESS'}
        return handler

    @pytest.fixture
    def executor(self, mock_booking_metadata_handler: AsyncMock) -> AtomicReleaseExecutor:
        return AtomicReleaseExecutor(booking_metadata_handler=mock_booking_metadata_handler)

    @pytest.mark.asyncio
    async def test_config_not_found_returns_all_failed(
        self,
        executor: AtomicReleaseExecutor,
    ) -> None:
        """
        Test that missing config returns all seats as failed.
        """
        # Mock Kvrocks client - config not found
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value=None)

        with patch(
            'src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            # Act
            result = await executor.execute_atomic_release(
                booking_id='test-booking-id',
                event_id=1,
                section='A',
                subsection=1,
                seat_positions=['1-1', '1-2'],
            )

            # Assert - all seats should be marked as failed
            assert result == {'1-1': False, '1-2': False}
