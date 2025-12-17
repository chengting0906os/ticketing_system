from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

import asyncpg
from opentelemetry import trace
from uuid_utils import UUID

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


if TYPE_CHECKING:
    pass


class BookingCommandRepoImpl(IBookingCommandRepo):
    """
    Booking Command Repository - Data Access Layer (Raw SQL with asyncpg)

    Architecture Rule: Repository NEVER commits!
    - Use case is responsible for transaction management (commit/rollback)
    - Repository only performs CRUD operations (add, update, flush)

    Performance: Using raw SQL with asyncpg for 2-3x faster operations
    """

    def __init__(self) -> None:
        self.tracer = trace.get_tracer(__name__)

    @staticmethod
    def _row_to_entity(row: asyncpg.Record) -> Booking:
        """
        Convert asyncpg Record to Booking entity

        Note: PostgreSQL returns uuid.UUID (stdlib), but Pydantic expects string or uuid_utils.UUID.
              We convert to string to ensure compatibility.
        """
        return Booking(
            buyer_id=row['buyer_id'],
            event_id=row['event_id'],
            section=row['section'],
            subsection=row['subsection'],
            quantity=row['quantity'],
            total_price=row['total_price'],
            seat_selection_mode=row['seat_selection_mode'] or 'manual',
            seat_positions=row['seat_positions'] or [],
            status=BookingStatus(row['status']),
            id=UUID(str(row['id'])),  # Convert stdlib uuid.UUID to uuid_utils.UUID
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            paid_at=row['paid_at'],
        )

    @Logger.io
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        """Query single booking (used for validation before command operations)"""
        async with (await get_asyncpg_pool()).acquire() as conn:
            # Convert string to UUID if needed (for asyncpg compatibility)
            booking_uuid = UUID(booking_id) if isinstance(booking_id, str) else booking_id

            row = await conn.fetchrow(
                """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at
                FROM booking
                WHERE id = $1
                """,
                booking_uuid,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    @Logger.io
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        """
        Update booking status to CANCELLED

        Args:
            booking: Booking entity with CANCELLED status

        Returns:
            Updated booking entity

        Raises:
            ValueError: If booking not found
        """
        async with (await get_asyncpg_pool()).acquire() as conn:
            # Convert string ID back to UUID for asyncpg
            booking_uuid = UUID(booking.id) if isinstance(booking.id, str) else booking.id

            result = await conn.execute(
                """
                UPDATE booking
                SET status = $1,
                    updated_at = $2
                WHERE id = $3
                """,
                booking.status.value,
                booking.updated_at,
                booking_uuid,
            )

            if result == 'UPDATE 0':
                raise ValueError(f'Booking with id {booking.id} not found')

            # Return the updated booking
            return booking

    @Logger.io
    async def update_status_to_failed(self, *, booking: Booking) -> None:
        async with (await get_asyncpg_pool()).acquire() as conn:
            # Convert string ID back to UUID for asyncpg
            booking_uuid = UUID(booking.id) if isinstance(booking.id, str) else booking.id

            result = await conn.execute(
                """
                UPDATE booking
                SET status = $1,
                    updated_at = $2
                WHERE id = $3
                """,
                booking.status.value,
                booking.updated_at,
                booking_uuid,
            )

            if result == 'UPDATE 0':
                raise ValueError(f'Booking with id {booking.id} not found')

    @Logger.io
    async def complete_booking_and_mark_tickets_sold_atomically(
        self, *, booking: Booking, ticket_ids: list[int]
    ) -> Booking:
        """
        Atomically update booking to COMPLETED and mark tickets as SOLD using CTE

        Uses Common Table Expression (CTE) to combine two operations in a single atomic statement:
        1. Update booking status to COMPLETED with paid_at timestamp
        2. Update all tickets to SOLD status

        PostgreSQL guarantees atomicity per statement - entire CTE succeeds or fails together.

        Args:
            booking: Booking entity with COMPLETED status and paid_at set
            ticket_ids: List of ticket IDs to mark as SOLD

        Returns:
            Updated booking entity
        """

        now = datetime.now(timezone.utc)

        async with (await get_asyncpg_pool()).acquire() as conn:
            # Convert string ID back to UUID for asyncpg
            booking_uuid = UUID(booking.id) if isinstance(booking.id, str) else booking.id

            # Use CTE to atomically update booking and tickets in a single statement
            booking_row = await conn.fetchrow(
                """
                WITH updated_tickets AS (
                    UPDATE ticket
                    SET status = 'sold',
                        updated_at = $1
                    WHERE id = ANY($2::int[])
                    RETURNING id
                ),
                updated_booking AS (
                    UPDATE booking
                    SET status = $3,
                        updated_at = $4,
                        paid_at = $5
                    WHERE id = $6
                    RETURNING id, buyer_id, event_id, section, subsection, quantity,
                              total_price, seat_selection_mode, seat_positions, status,
                              created_at, updated_at, paid_at
                )
                SELECT * FROM updated_booking
                """,
                now,
                ticket_ids if ticket_ids else [],
                booking.status.value,
                booking.updated_at,
                booking.paid_at,
                booking_uuid,
            )

            if not booking_row:
                raise ValueError(f'Booking with id {booking.id} not found')

            Logger.base.info(
                f'💳 [ATOMIC_PAY] Updated booking {booking.id} to COMPLETED and {len(ticket_ids)} tickets to SOLD'
            )

            return self._row_to_entity(booking_row)

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List[TicketRef]:
        """
        Query tickets associated with booking (used for command operations)

        Uses booking's event_id, section, subsection, and seat_positions to find matching tickets
        via the unique constraint (event_id, section, subsection, row_number, seat_number)

        Args:
            booking_id: Booking ID

        Returns:
            List of ticket references with full details
        """
        async with (await get_asyncpg_pool()).acquire() as conn:
            # Convert string to UUID if needed (for asyncpg compatibility)
            booking_uuid = UUID(booking_id) if isinstance(booking_id, str) else booking_id

            # First, get booking info
            booking_row = await conn.fetchrow(
                """
                SELECT event_id, section, subsection, seat_positions
                FROM booking
                WHERE id = $1
                """,
                booking_uuid,
            )

            if not booking_row or not booking_row['seat_positions']:
                return []

            # Query tickets using booking's info and seat_positions
            # seat_positions format: ["1-1", "1-2"] (row-seat)
            rows = await conn.fetch(
                """
                SELECT t.id, t.event_id, t.section, t.subsection, t.row_number, t.seat_number,
                       t.price, t.status, t.created_at, t.updated_at
                FROM ticket t
                WHERE t.event_id = $1
                  AND t.section = $2
                  AND t.subsection = $3
                  AND (t.row_number::text || '-' || t.seat_number::text) = ANY($4::text[])
                ORDER BY t.id
                """,
                booking_row['event_id'],
                booking_row['section'],
                booking_row['subsection'],
                booking_row['seat_positions'],
            )

            tickets = []
            for row in rows:
                ticket = TicketRef(
                    event_id=row['event_id'],
                    section=row['section'],
                    subsection=row['subsection'],
                    row=row['row_number'],
                    seat=row['seat_number'],
                    price=row['price'],
                    status=TicketStatus(row['status']),
                    id=row['id'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                )
                tickets.append(ticket)

            return tickets

    @Logger.io
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
        """
        Directly create booking in PENDING_PAYMENT status with tickets in RESERVED status.
        Called by Seat Reservation Service after successful Kvrocks reservation.

        Uses CTE to atomically:
        1. Create booking record (status=PENDING_PAYMENT, total_price, seat_positions)
        2. Update ticket records (status=RESERVED) with buyer_id and timestamps
        3. Return both booking and tickets in single query

        Args:
            booking_id: UUID7 booking ID (from CreateBookingUseCase)
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            seat_selection_mode: 'manual' or 'best_available'
            reserved_seats: List of reserved seat identifiers (format: "row-seat" like "1-1")
            total_price: Sum of all seat prices

        Returns:
            Dict with keys:
            - booking: Created/existing booking entity
            - tickets: List of ticket references

        Raises:
            ValueError: If booking already exists or transaction fails
        """
        # Defensive validation: Ensure seat IDs are in correct format "row-seat" (e.g., "1-1")
        # NOT "section-subsection-row-seat" (e.g., "A-6-1-1")
        for seat_id in reserved_seats:
            parts = seat_id.split('-')
            if len(parts) != 2:
                raise ValueError(
                    f'Invalid seat_id format: "{seat_id}". '
                    f'Expected format "row-seat" (e.g., "1-1"), got {len(parts)} parts. '
                    f'This usually means Reservation Service sent wrong format.'
                )
            try:
                int(parts[0])  # row must be integer
                int(parts[1])  # seat must be integer
            except ValueError:
                raise ValueError(
                    f'Invalid seat_id format: "{seat_id}". '
                    f'Row and seat must be integers. Expected format "row-seat" (e.g., "1-1").'
                )

        with self.tracer.start_as_current_span(
            'repo.create_booking_with_tickets',
            attributes={
                'booking.id': str(booking_id),
                'event.id': event_id,
                'buyer.id': buyer_id,
                'seat.section': section,
                'seat.subsection': subsection,
                'seat.mode': seat_selection_mode,
                'seats.count': len(reserved_seats),
                'booking.total_price': total_price,
                'db.system': 'postgresql',
                'db.operation': 'insert',
            },
        ):
            now = datetime.now(timezone.utc)

            async with (await get_asyncpg_pool()).acquire() as conn:
                # Convert string to UUID if needed (for asyncpg compatibility)
                booking_uuid = UUID(booking_id) if isinstance(booking_id, str) else booking_id

                # Check if booking already exists (idempotency)
                existing = await conn.fetchrow(
                    """
                    SELECT id FROM booking WHERE id = $1
                    """,
                    booking_uuid,
                )

                if existing:
                    Logger.base.warning(
                        f'⚠️ [IDEMPOTENCY] Booking {booking_id} already exists - returning existing booking and tickets'
                    )
                    # Return existing booking and tickets
                    existing_booking = await self.get_by_id(booking_id=booking_uuid)
                    existing_tickets = await self.get_tickets_by_booking_id(booking_id=booking_uuid)
                    return {
                        'booking': existing_booking,
                        'tickets': existing_tickets,
                    }

                # Use CTE to atomically create booking and update tickets, returning both
                result = await conn.fetch(
                    """
                    WITH inserted_booking AS (
                        INSERT INTO booking (
                            id, buyer_id, event_id, section, subsection, quantity,
                            total_price, seat_selection_mode, seat_positions, status,
                            created_at, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        RETURNING id, buyer_id, event_id, section, subsection, quantity,
                                  total_price, seat_selection_mode, seat_positions, status,
                                  created_at, updated_at, paid_at
                    ),
                    updated_tickets AS (
                        UPDATE ticket
                        SET status = 'reserved',
                            buyer_id = $2,
                            updated_at = $11,
                            reserved_at = $11
                        WHERE event_id = $3
                          AND section = $4
                          AND subsection = $5
                          AND (row_number::text || '-' || seat_number::text) = ANY($9::text[])
                          AND status = 'available'
                        RETURNING id, event_id, section, subsection, row_number, seat_number,
                                  price, status, buyer_id, created_at, updated_at, reserved_at
                    )
                    SELECT
                        'booking' as type,
                        b.id, b.buyer_id, b.event_id, b.section, b.subsection, b.quantity,
                        b.total_price, b.seat_selection_mode, b.seat_positions, b.status,
                        b.created_at, b.updated_at, b.paid_at,
                        NULL::int as ticket_id, NULL::int as row_number, NULL::int as seat_number,
                        NULL::int as price, NULL::text as ticket_status, NULL::int as ticket_buyer_id,
                        NULL::timestamp as ticket_created_at, NULL::timestamp as ticket_updated_at, NULL::timestamp as reserved_at
                    FROM inserted_booking b
                    UNION ALL
                    SELECT
                        'ticket' as type,
                        NULL, NULL, t.event_id, t.section, t.subsection, NULL,
                        NULL, NULL, NULL, NULL,
                        NULL, NULL, NULL,
                        t.id, t.row_number, t.seat_number,
                        t.price, t.status, t.buyer_id,
                        t.created_at, t.updated_at, t.reserved_at
                    FROM updated_tickets t
                    """,
                    booking_uuid,  # $1
                    buyer_id,  # $2
                    event_id,  # $3
                    section,  # $4
                    subsection,  # $5
                    len(reserved_seats),  # $6 - quantity
                    total_price,  # $7
                    seat_selection_mode,  # $8
                    reserved_seats,  # $9 - seat_positions
                    BookingStatus.PENDING_PAYMENT.value,  # $10
                    now,  # $11 - created_at
                    now,  # $12 - updated_at
                )

                if not result:
                    raise ValueError(f'Failed to create booking {booking_id}')

                # Separate booking and ticket rows
                booking_row = None
                ticket_rows = []

                for row in result:
                    if row['type'] == 'booking':
                        booking_row = row
                    else:
                        ticket_rows.append(row)

                if not booking_row:
                    raise ValueError(f'Failed to create booking {booking_id}')

                created_booking = self._row_to_entity(booking_row)

                # Convert ticket rows to TicketRef entities
                tickets = []
                for row in ticket_rows:
                    ticket = TicketRef(
                        event_id=row['event_id'],
                        section=row['section'],
                        subsection=row['subsection'],
                        row=row['row_number'],
                        seat=row['seat_number'],
                        price=row['price'],
                        status=TicketStatus(row['ticket_status']),
                        buyer_id=row['ticket_buyer_id'],
                        id=row['ticket_id'],
                        created_at=row['ticket_created_at'],
                        updated_at=row['ticket_updated_at'],
                        reserved_at=row['reserved_at'],
                    )
                    tickets.append(ticket)

                # Record span event: all tickets are now reserved in PostgreSQL
                span = trace.get_current_span()
                span.add_event(
                    'tickets.all_reserved',
                    attributes={
                        'tickets.reserved_count': len(tickets),
                        'tickets.total_price': total_price,
                    },
                )
                span.set_attribute('tickets.reserved_count', len(tickets))

                Logger.base.info(
                    f'✅ [DIRECT-CREATE] Created booking {booking_id} in PENDING_PAYMENT with {len(tickets)} RESERVED tickets '
                    f'(total: {total_price}) - called by Seat Reservation Service'
                )

                return {
                    'booking': created_booking,
                    'tickets': tickets,
                }

    @Logger.io
    async def create_failed_booking_directly(
        self,
        *,
        booking_id: UUID,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        seat_positions: list[str],
        quantity: int,
    ) -> Booking:
        """
        Directly create booking in FAILED status (no tickets).
        Called when seat reservation fails - booking never existed in PostgreSQL.

        Args:
            booking_id: UUID7 booking ID (from Kafka event)
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            seat_selection_mode: 'manual' or 'best_available'
            seat_positions: Originally requested seat positions
            quantity: Originally requested quantity

        Returns:
            Created booking entity with FAILED status

        Raises:
            ValueError: If booking already exists
        """
        with self.tracer.start_as_current_span(
            'repo.create_failed_booking',
            attributes={
                'booking.id': str(booking_id),
                'event.id': event_id,
                'buyer.id': buyer_id,
                'seat.section': section,
                'seat.subsection': subsection,
                'booking.status': 'failed',
                'db.system': 'postgresql',
                'db.operation': 'insert',
            },
        ):
            now = datetime.now(timezone.utc)

            async with (await get_asyncpg_pool()).acquire() as conn:
                # Convert string to UUID if needed (for asyncpg compatibility)
                booking_uuid = UUID(booking_id) if isinstance(booking_id, str) else booking_id

                # Check if booking already exists (idempotency)
                existing = await conn.fetchrow(
                    """
                    SELECT id, status FROM booking WHERE id = $1
                    """,
                    booking_uuid,
                )

                if existing:
                    Logger.base.warning(
                        f'⚠️ [IDEMPOTENCY] Booking {booking_id} already exists with status {existing["status"]}'
                    )
                    # Return existing booking
                    existing_booking = await self.get_by_id(booking_id=booking_uuid)
                    if not existing_booking:
                        raise ValueError(f'Booking {booking_id} exists but could not be retrieved')
                    return existing_booking

                # Insert FAILED booking (no tickets, total_price=0)
                booking_row = await conn.fetchrow(
                    """
                    INSERT INTO booking (
                        id, buyer_id, event_id, section, subsection, quantity,
                        total_price, seat_selection_mode, seat_positions, status,
                        created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    RETURNING id, buyer_id, event_id, section, subsection, quantity,
                              total_price, seat_selection_mode, seat_positions, status,
                              created_at, updated_at, paid_at
                    """,
                    booking_uuid,  # $1
                    buyer_id,  # $2
                    event_id,  # $3
                    section,  # $4
                    subsection,  # $5
                    quantity,  # $6
                    0,  # $7 - total_price = 0 for failed bookings
                    seat_selection_mode,  # $8
                    seat_positions,  # $9
                    BookingStatus.FAILED.value,  # $10
                    now,  # $11 - created_at
                    now,  # $12 - updated_at
                )

                if not booking_row:
                    raise ValueError(f'Failed to create FAILED booking {booking_id}')

                created_booking = self._row_to_entity(booking_row)

                Logger.base.info(
                    f'✅ [DIRECT-CREATE-FAILED] Created booking {booking_id} in FAILED status '
                    f'(requested {quantity} seats in {section}-{subsection})'
                )

                return created_booking
