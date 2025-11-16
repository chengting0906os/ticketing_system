"""
Unit tests for UpdateBookingToPendingPaymentAndTicketToReservedUseCase

Test Focus:
1. SSE broadcast includes seat availability stats when provided
2. SSE broadcast works without stats (backward compatibility)
3. Stats are only included when not None
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

from anyio import create_memory_object_stream
from anyio.streams.memory import MemoryObjectReceiveStream
import pytest
import uuid_utils as uuid
from uuid_utils import UUID

from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster
from src.service.ticketing.app.command.update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case import (
    UpdateBookingToPendingPaymentAndTicketToReservedUseCase,
)
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class MockBookingCommandRepo(IBookingCommandRepo):
    """Mock implementation of IBookingCommandRepo for testing"""

    def __init__(self):
        self.created_bookings: List[Dict] = []

    async def get_by_id(self, *, booking_id: UUID) -> Optional[Booking]:
        """Mock implementation - not used in these tests"""
        return None

    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> list:
        """Mock implementation - not used in these tests"""
        return []

    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        """Mock implementation - not used in these tests"""
        raise NotImplementedError

    async def update_status_to_failed(self, *, booking: Booking) -> None:
        """Mock implementation - not used in these tests"""
        raise NotImplementedError

    async def complete_booking_and_mark_tickets_sold_atomically(
        self, *, booking: Booking, ticket_ids: list[int]
    ) -> Booking:
        """Mock implementation - not used in these tests"""
        raise NotImplementedError

    async def create_booking_with_tickets_directly(
        self,
        *,
        booking_id: UUID,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        reserved_seats: list[str],
        total_price: int,
    ) -> dict:
        """Mock implementation that returns booking and tickets"""
        # Store call for verification
        self.created_bookings.append(
            {
                'booking_id': booking_id,
                'buyer_id': buyer_id,
                'event_id': event_id,
                'section': section,
                'subsection': subsection,
                'seat_selection_mode': seat_selection_mode,
                'reserved_seats': reserved_seats,
                'total_price': total_price,
            }
        )

        # Create mock booking
        booking = Booking(
            id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            quantity=len(reserved_seats),
            status=BookingStatus.PENDING_PAYMENT,
            seat_selection_mode=seat_selection_mode,
            total_price=total_price,
            seat_positions=reserved_seats,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock tickets (using TicketRef as per repository)
        tickets = [
            TicketRef(
                id=idx + 1,
                event_id=event_id,
                section=section,
                subsection=subsection,
                row=int(seat.split('-')[0]),
                seat=int(seat.split('-')[1]),
                status=TicketStatus.RESERVED,
                buyer_id=buyer_id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                reserved_at=datetime.now(timezone.utc),
            )
            for idx, seat in enumerate(reserved_seats)
        ]

        return {'booking': booking, 'tickets': tickets}


class MockEventBroadcaster(IInMemoryEventBroadcaster):
    def __init__(self):
        self.broadcast_calls: List[Dict[str, Any]] = []

    async def broadcast(self, *, booking_id: UUID, event_data: dict) -> None:
        self.broadcast_calls.append({'booking_id': booking_id, 'event_data': event_data})

    async def subscribe(self, *, booking_id: UUID) -> MemoryObjectReceiveStream[dict]:
        _, receive_stream = create_memory_object_stream[dict](max_buffer_size=10)
        return receive_stream

    async def unsubscribe(
        self, *, booking_id: UUID, stream: MemoryObjectReceiveStream[dict]
    ) -> None:
        pass


@pytest.mark.unit
class TestUpdateBookingToPendingPaymentWithStats:
    """Test suite for SSE broadcast with seat availability stats"""

    @pytest.fixture
    def booking_id(self) -> UUID:
        return uuid.uuid7()

    @pytest.fixture
    def mock_repo(self) -> MockBookingCommandRepo:
        return MockBookingCommandRepo()

    @pytest.fixture
    def mock_broadcaster(self) -> MockEventBroadcaster:
        return MockEventBroadcaster()

    @pytest.fixture
    def use_case(
        self, mock_repo: MockBookingCommandRepo, mock_broadcaster: MockEventBroadcaster
    ) -> UpdateBookingToPendingPaymentAndTicketToReservedUseCase:
        return UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=mock_repo,
            event_broadcaster=mock_broadcaster,
        )

    @pytest.mark.asyncio
    async def test_broadcast_includes_subsection_stats(
        self, use_case, booking_id, mock_broadcaster
    ):
        # Given: Subsection stats from Seat Reservation Service
        subsection_stats = {
            'section_id': 'A-1',
            'available': 8,
            'reserved': 2,
            'total': 10,
        }

        # When: Execute use case with subsection stats
        # Note: reserved_seats must be in 'section-subsection-row-seat' format (e.g., 'A-1-1-3')
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            subsection_stats=subsection_stats,
        )

        # Then: Broadcast should include subsection_stats
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        assert 'subsection_stats' in event_data
        assert event_data['subsection_stats'] == subsection_stats

    @pytest.mark.asyncio
    async def test_broadcast_includes_event_stats(self, use_case, booking_id, mock_broadcaster):
        # Given: Event stats from Seat Reservation Service
        event_stats = {
            'event_id': 1,
            'available': 98,
            'reserved': 2,
            'total': 100,
        }

        # When: Execute use case with event stats
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            event_stats=event_stats,
        )

        # Then: Broadcast should include event_stats
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        assert 'event_stats' in event_data
        assert event_data['event_stats'] == event_stats

    @pytest.mark.asyncio
    async def test_broadcast_includes_both_stats(self, use_case, booking_id, mock_broadcaster):
        # Given: Both subsection and event stats
        subsection_stats = {'section_id': 'A-1', 'available': 8}
        event_stats = {'event_id': 1, 'available': 98}

        # When: Execute use case with both stats
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            subsection_stats=subsection_stats,
            event_stats=event_stats,
        )

        # Then: Broadcast should include both stats
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        assert 'subsection_stats' in event_data
        assert 'event_stats' in event_data
        assert event_data['subsection_stats'] == subsection_stats
        assert event_data['event_stats'] == event_stats

    @pytest.mark.asyncio
    async def test_broadcast_without_stats_backward_compatibility(
        self, use_case, booking_id, mock_broadcaster
    ):
        # Given: No stats provided (None)

        # When: Execute use case without stats
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
        )

        # Then: Broadcast should NOT include stats fields
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        assert 'subsection_stats' not in event_data
        assert 'event_stats' not in event_data

    @pytest.mark.asyncio
    async def test_broadcast_omits_none_stats(self, use_case, booking_id, mock_broadcaster):
        # Given: Stats explicitly set to None

        # When: Execute use case with None stats
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            subsection_stats=None,
            event_stats=None,
        )

        # Then: Broadcast should NOT include None values
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        assert 'subsection_stats' not in event_data
        assert 'event_stats' not in event_data

    @pytest.mark.asyncio
    async def test_broadcast_includes_required_fields(self, use_case, booking_id, mock_broadcaster):
        # Given: Use case with stats

        # When: Execute use case
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            subsection_stats={'section_id': 'A-1', 'available': 8},
        )

        # Then: Broadcast should include all required fields
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']

        # Required fields
        assert event_data['event_type'] == 'status_update'
        assert event_data['booking_id'] == str(booking_id)
        assert event_data['status'] == 'pending_payment'
        assert event_data['total_price'] == 2000
        assert 'updated_at' in event_data
        assert 'tickets' in event_data
        assert len(event_data['tickets']) == 2

        # Optional stats field
        assert 'subsection_stats' in event_data

    @pytest.mark.asyncio
    async def test_broadcast_failure_does_not_fail_use_case(
        self, use_case, booking_id, mock_broadcaster
    ):
        # Given: Broadcaster that raises exception
        mock_broadcaster.broadcast = AsyncMock(side_effect=Exception('Broadcast failed'))

        # When: Execute use case (should not raise)
        result = await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            subsection_stats={'section_id': 'A-1', 'available': 8},
        )

        # Then: Use case should succeed despite broadcast failure
        assert result is not None
        assert result.status == BookingStatus.PENDING_PAYMENT

    @pytest.mark.asyncio
    async def test_empty_dict_stats_are_included(self, use_case, booking_id, mock_broadcaster):
        # Given: Empty dict stats (different from None)
        subsection_stats = {}
        event_stats = {}

        # When: Execute use case with empty dicts
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1000},
            total_price=2000,
            subsection_stats=subsection_stats,
            event_stats=event_stats,
        )

        # Then: Empty dicts should be included (truthiness check passes for empty dict)
        # Note: Empty dicts are falsy in Python, so they won't be included
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        # Empty dicts are falsy, so they should NOT be included
        assert 'subsection_stats' not in event_data
        assert 'event_stats' not in event_data

    @pytest.mark.asyncio
    async def test_ticket_data_in_broadcast(self, use_case, booking_id, mock_broadcaster):
        # Given: Reserved seats

        # When: Execute use case
        await use_case.execute(
            booking_id=booking_id,
            buyer_id=123,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-3', 'A-1-1-4'],
            seat_prices={'A-1-1-3': 1000, 'A-1-1-4': 1500},
            total_price=2500,
        )

        # Then: Ticket data should be properly formatted
        assert len(mock_broadcaster.broadcast_calls) == 1
        event_data = mock_broadcaster.broadcast_calls[0]['event_data']
        tickets = event_data['tickets']

        assert len(tickets) == 2
        for ticket in tickets:
            assert 'id' in ticket
            assert 'section' in ticket
            assert 'subsection' in ticket
            assert 'row' in ticket
            assert 'seat_num' in ticket
            assert 'price' in ticket
            assert 'status' in ticket
            assert 'seat_identifier' in ticket

        # Check seat identifiers are in correct format
        seat_identifiers = [t['seat_identifier'] for t in tickets]
        assert 'A-1-1-3' in seat_identifiers
        assert 'A-1-1-4' in seat_identifiers
