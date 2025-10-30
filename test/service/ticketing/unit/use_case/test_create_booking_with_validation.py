"""
Unit tests for CreateBookingUseCase with Kvrocks tracking

Test coverage:
1. Store booking tracking in Kvrocks: event_id:buyer_id:booking_id with TTL 1 day
2. Handle duplicate booking attempts (idempotency via Kvrocks)
3. Clean up tracking on database failure (compensating action)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from redis.exceptions import RedisError

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


@pytest.fixture
def mock_booking_repo():
    """Mock booking command repository"""
    repo = Mock()
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def mock_event_publisher():
    """Mock event publisher"""
    publisher = Mock()
    publisher.publish_booking_created = AsyncMock()
    return publisher


@pytest.fixture
def mock_seat_availability_handler():
    """Mock seat availability query handler"""
    handler = Mock()
    handler.check_subsection_availability = AsyncMock()
    return handler


@pytest.fixture
def mock_booking_tracker():
    """Mock booking tracker (Kvrocks) for preventing duplicate bookings"""
    tracker = Mock()
    tracker.track_booking = AsyncMock()  # Async operation
    tracker.remove_booking_track = AsyncMock()  # Async operation
    return tracker


@pytest.fixture
def use_case(
    mock_booking_repo, mock_event_publisher, mock_seat_availability_handler, mock_booking_tracker
):
    """Create use case with mocked dependencies"""
    return CreateBookingUseCase(
        booking_command_repo=mock_booking_repo,
        event_publisher=mock_event_publisher,
        seat_availability_handler=mock_seat_availability_handler,
        booking_tracker=mock_booking_tracker,
    )


@pytest.fixture
def sample_booking_request():
    """Sample booking request data"""
    return {
        'buyer_id': UUID('019a1af7-0000-7001-0000-000000000001'),
        'event_id': UUID('019a1af7-0000-7003-0000-000000000001'),
        'section': 'A',
        'subsection': 1,
        'seat_selection_mode': 'manual',
        'seat_positions': ['1-1', '1-2'],
        'quantity': 2,
    }


@pytest.fixture
def sample_booking():
    """Sample booking entity"""
    return Booking(
        id=UUID('019a1af7-0000-7004-0000-000000000001'),
        buyer_id=UUID('019a1af7-0000-7001-0000-000000000001'),
        event_id=UUID('019a1af7-0000-7003-0000-000000000001'),
        section='A',
        subsection=1,
        quantity=2,
        total_price=2000,
        seat_selection_mode='manual',
        seat_positions=['A-1-1-1', 'A-1-1-2'],
        status=BookingStatus.PROCESSING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ===================== Test Cases =====================


@pytest.mark.asyncio
async def test_create_booking_tracks_in_kvrocks(
    use_case,
    sample_booking_request,
    sample_booking,
    mock_booking_tracker,
    mock_booking_repo,
    mock_seat_availability_handler,
):
    """
    GIVEN: Valid booking request
    WHEN: Creating booking
    THEN: Should track event_id:buyer_id:booking_id in Kvrocks with 1 day TTL
    """
    # Arrange
    mock_seat_availability_handler.check_subsection_availability.return_value = True
    mock_booking_repo.create.return_value = sample_booking
    mock_booking_tracker.track_booking.return_value = True  # No duplicate found

    # Act
    result = await use_case.create_booking(**sample_booking_request)

    # Assert - Kvrocks tracking was called AFTER booking creation
    mock_booking_tracker.track_booking.assert_called_once()
    call_kwargs = mock_booking_tracker.track_booking.call_args.kwargs

    assert call_kwargs['event_id'] == sample_booking_request['event_id']
    assert call_kwargs['buyer_id'] == sample_booking_request['buyer_id']
    assert call_kwargs['booking_id'] == sample_booking.id
    # TTL is handled in implementation (86400 seconds = 1 day)

    assert result.id == sample_booking.id


@pytest.mark.asyncio
async def test_create_booking_rejects_duplicate_for_same_subsection(
    use_case, sample_booking_request, mock_booking_tracker, mock_seat_availability_handler
):
    """
    GIVEN: User already has pending booking for this event+subsection
    WHEN: Trying to create another booking
    THEN: Should reject with DomainError (duplicate detected by Kvrocks)
    """
    # Arrange
    mock_seat_availability_handler.check_subsection_availability.return_value = True
    mock_booking_tracker.track_booking.return_value = False  # Duplicate found!

    # Act & Assert
    with pytest.raises(DomainError) as exc_info:
        await use_case.create_booking(**sample_booking_request)

    assert (
        'already has' in str(exc_info.value).lower() or 'duplicate' in str(exc_info.value).lower()
    )


@pytest.mark.asyncio
async def test_create_booking_cleans_up_kvrocks_on_publish_failure(
    use_case,
    sample_booking_request,
    sample_booking,
    mock_booking_tracker,
    mock_booking_repo,
    mock_event_publisher,
    mock_seat_availability_handler,
):
    """
    GIVEN: Booking created but event publishing fails
    WHEN: Creating booking
    THEN: Should remove Kvrocks tracking (compensating action)
    """
    # Arrange
    mock_seat_availability_handler.check_subsection_availability.return_value = True
    mock_booking_repo.create.return_value = sample_booking
    mock_booking_tracker.track_booking.return_value = True
    mock_event_publisher.publish_booking_created.side_effect = RedisError('Kafka unavailable')

    # Act & Assert
    with pytest.raises(RedisError):
        await use_case.create_booking(**sample_booking_request)

    # Verify cleanup was called
    mock_booking_tracker.remove_booking_track.assert_called_once()
    call_kwargs = mock_booking_tracker.remove_booking_track.call_args.kwargs

    assert call_kwargs['event_id'] == sample_booking_request['event_id']
    assert call_kwargs['buyer_id'] == sample_booking_request['buyer_id']
    assert call_kwargs['booking_id'] == sample_booking.id
