"""
Integration test for Reservation Service PostgreSQL booking operations

Tests the PostgreSQL write operations that Reservation Service now handles:
1. complete_booking_and_mark_tickets_sold_atomically - Payment finalization
2. update_status_to_cancelled - Booking cancellation
3. get_by_id - Booking query
4. get_tickets_by_booking_id - Ticket query
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import uuid_utils as uuid

from src.platform.database.asyncpg_setting import get_asyncpg_pool
from src.service.reservation.driven_adapter.repo.booking_command_repo_impl import (
    BookingCommandRepoImpl,
)
from src.service.ticketing.domain.entity.booking_entity import BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus


@pytest.fixture
async def booking_repo() -> BookingCommandRepoImpl:
    """Create booking repository instance"""
    return BookingCommandRepoImpl()


@pytest.fixture
async def test_event_with_tickets(clean_database: None) -> AsyncGenerator[None, None]:
    """Create test event with tickets.

    Depends on clean_database to ensure tables are cleaned before setup.
    """
    pool = await get_asyncpg_pool()
    async with pool.acquire() as conn:
        # Create test user for foreign key constraint
        user_id = await conn.fetchval(
            """
            INSERT INTO "user" (name, email, hashed_password, role, is_active, is_superuser, is_verified)
            VALUES ('Test Seller', 'test_booking_seller@example.com', 'hashed_password', 'seller', true, false, true)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """
        )

        # Create test event with event_id=1
        await conn.execute(
            """
            INSERT INTO event (id, name, description, seller_id, is_active, status, venue_name, seating_config)
            VALUES (1, 'Test Event', 'Test Description', $1, true, 'available', 'Test Venue', '{}')
            ON CONFLICT (id) DO NOTHING
            """,
            user_id,
        )

        # Create test tickets in section TEST, subsection 1
        for row in range(1, 7):  # Rows 1-6
            for seat in range(1, 5):  # Seats 1-4
                await conn.execute(
                    """
                    INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                    VALUES (1, 'TEST', 1, $1, $2, 1000, 'available')
                    ON CONFLICT (event_id, section, subsection, row_number, seat_number) DO NOTHING
                    """,
                    row,
                    seat,
                )

    yield

    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM booking WHERE section = 'TEST' AND event_id = 1")
        await conn.execute("DELETE FROM ticket WHERE section = 'TEST' AND event_id = 1")
        await conn.execute('DELETE FROM event WHERE id = 1')


class TestBookingPostgreSQLOperations:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_booking_with_tickets_then_complete_payment(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        # Given: Create a booking with tickets (test event has tickets 1-1 through 6-4)
        booking_id = uuid.uuid7()
        buyer_id = 99999
        event_id = 1  # Use existing event
        section = 'TEST'
        subsection = 1
        seat_selection_mode = 'manual'
        reserved_seats = ['1-1', '1-2', '1-3']
        total_price = 3000

        result = await booking_repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=reserved_seats,
            total_price=total_price,
        )

        # Verify booking created with PENDING_PAYMENT status
        booking = result['booking']
        tickets = result['tickets']
        assert booking.id == booking_id
        assert booking.status == BookingStatus.PENDING_PAYMENT
        assert booking.buyer_id == buyer_id
        assert booking.total_price == total_price
        assert len(tickets) == 3

        # Verify tickets created with RESERVED status
        ticket_ids = [ticket.id for ticket in tickets]
        for ticket in tickets:
            assert ticket.status == TicketStatus.RESERVED
            assert ticket.buyer_id == buyer_id

        # When: Complete payment
        updated_booking = await booking_repo.complete_booking_and_mark_tickets_sold_atomically(
            booking_id=booking_id,
            ticket_ids=ticket_ids,
        )

        # Then: Booking status updated to COMPLETED
        assert updated_booking.status == BookingStatus.COMPLETED
        assert updated_booking.paid_at is not None

        # Verify tickets updated to SOLD
        tickets_after_payment = await booking_repo.get_tickets_by_booking_id(booking_id=booking_id)
        for ticket in tickets_after_payment:
            assert ticket.status == TicketStatus.SOLD

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_booking_then_cancel(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        """Test creating booking then cancelling it"""
        # Given: Create a booking with tickets
        booking_id = uuid.uuid7()
        buyer_id = 99999
        event_id = 1  # Use existing event
        section = 'TEST'
        subsection = 1
        seat_selection_mode = 'manual'
        reserved_seats = ['2-1', '2-2']
        total_price = 2000

        result = await booking_repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=reserved_seats,
            total_price=total_price,
        )

        booking = result['booking']
        assert booking.status == BookingStatus.PENDING_PAYMENT

        # When: Cancel booking
        cancelled_booking = await booking_repo.update_status_to_cancelled(booking_id=booking_id)

        # Then: Booking status updated to CANCELLED
        assert cancelled_booking.status == BookingStatus.CANCELLED
        assert cancelled_booking.paid_at is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_failed_booking(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        """Test creating a failed booking (no tickets reserved)"""
        # Given: Failed reservation parameters (using non-existent seats)
        booking_id = uuid.uuid7()
        buyer_id = 99999
        event_id = 1  # Use existing event
        section = 'TEST'
        subsection = 1
        seat_selection_mode = 'manual'
        seat_positions = ['99-99', '99-98']  # Non-existent seats
        quantity = 2

        # When: Create failed booking
        failed_booking = await booking_repo.create_failed_booking_directly(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            seat_positions=seat_positions,
            quantity=quantity,
        )

        # Then: Booking created with FAILED status
        assert failed_booking.status == BookingStatus.FAILED
        assert failed_booking.id == booking_id
        assert failed_booking.buyer_id == buyer_id
        assert failed_booking.seat_positions == seat_positions  # Requested seats recorded

        # Verify no actual tickets reserved (since seats don't exist)
        tickets = await booking_repo.get_tickets_by_booking_id(booking_id=booking_id)
        assert len(tickets) == 0  # Non-existent seats = no tickets found

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_booking_by_id(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        # Given: Create a booking
        booking_id = uuid.uuid7()
        buyer_id = 99999
        event_id = 1  # Use existing event
        section = 'TEST'
        subsection = 1
        seat_selection_mode = 'best_available'
        reserved_seats = ['4-1']
        total_price = 1000

        await booking_repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=reserved_seats,
            total_price=total_price,
        )

        # When: Query by ID
        queried_booking = await booking_repo.get_by_id(booking_id=booking_id)

        # Then: Booking found and matches
        assert queried_booking is not None
        assert queried_booking.id == booking_id
        assert queried_booking.buyer_id == buyer_id
        assert queried_booking.event_id == event_id
        assert queried_booking.status == BookingStatus.PENDING_PAYMENT

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_booking_by_id_not_found(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        # Given: Non-existent booking ID
        non_existent_id = uuid.uuid7()

        # When: Query by ID
        result = await booking_repo.get_by_id(booking_id=non_existent_id)

        # Then: Returns None
        assert result is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_tickets_by_booking_id(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        # Given: Create a booking with multiple tickets
        booking_id = uuid.uuid7()
        buyer_id = 99999
        event_id = 1  # Use existing event
        section = 'TEST'
        subsection = 1
        seat_selection_mode = 'manual'
        reserved_seats = ['5-1', '5-2', '5-3', '5-4']
        total_price = 4000

        await booking_repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=reserved_seats,
            total_price=total_price,
        )

        # When: Query tickets by booking ID
        tickets = await booking_repo.get_tickets_by_booking_id(booking_id=booking_id)

        # Then: All tickets returned
        assert len(tickets) == 4
        for ticket in tickets:
            assert ticket.buyer_id == buyer_id
            assert ticket.status == TicketStatus.RESERVED
            assert ticket.section == section
            assert ticket.subsection == subsection

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_payment_atomicity(
        self, booking_repo: BookingCommandRepoImpl, test_event_with_tickets: Any
    ) -> None:
        # Given: Create a booking with tickets
        booking_id = uuid.uuid7()
        buyer_id = 99999
        event_id = 1  # Use existing event
        section = 'TEST'
        subsection = 1
        seat_selection_mode = 'manual'
        reserved_seats = ['6-1', '6-2']
        total_price = 2000

        result = await booking_repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=reserved_seats,
            total_price=total_price,
        )

        ticket_ids = [ticket.id for ticket in result['tickets']]

        # When: Complete payment
        updated_booking = await booking_repo.complete_booking_and_mark_tickets_sold_atomically(
            booking_id=booking_id,
            ticket_ids=ticket_ids,
        )

        # Then: Both booking and tickets updated atomically
        # Query booking directly from DB
        pool = await get_asyncpg_pool()
        async with pool.acquire() as conn:
            # Check booking status
            booking_row = await conn.fetchrow(
                'SELECT status, paid_at FROM booking WHERE id = $1',
                updated_booking.id,
            )
            assert booking_row['status'] == BookingStatus.COMPLETED.value
            assert booking_row['paid_at'] is not None

            # Check all tickets status (use seat positions to find tickets)
            ticket_rows = await conn.fetch(
                """
                SELECT status FROM ticket
                WHERE event_id = $1 AND section = $2 AND subsection = $3
                  AND buyer_id = $4 AND status = $5
                """,
                event_id,
                section,
                subsection,
                buyer_id,
                TicketStatus.SOLD.value,
            )
            assert len(ticket_rows) == 2
