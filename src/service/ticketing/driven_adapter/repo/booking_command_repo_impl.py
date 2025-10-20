from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

from opentelemetry import trace

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


if TYPE_CHECKING:
    pass


class IBookingCommandRepoImpl(IBookingCommandRepo):
    """
    Booking Command Repository - Data Access Layer (Raw SQL with asyncpg)

    Architecture Rule: Repository NEVER commits!
    - Use case is responsible for transaction management (commit/rollback)
    - Repository only performs CRUD operations (add, update, flush)

    Performance: Using raw SQL with asyncpg for 2-3x faster operations
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @staticmethod
    def _row_to_entity(row) -> Booking:
        """
        Convert asyncpg Record to Booking entity
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
            id=row['id'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            paid_at=row['paid_at'],
        )

    @Logger.io
    async def get_by_id(self, *, booking_id: int) -> Booking | None:
        """查詢單筆 booking（用於 command 操作前的驗證）"""
        async with (await get_asyncpg_pool()).acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at
                FROM booking
                WHERE id = $1
                """,
                booking_id,
            )

            if not row:
                return None

            return self._row_to_entity(row)

    async def create(self, *, booking: Booking) -> Booking:
        with self.tracer.start_as_current_span('db.booking.create') as span:
            async with (await get_asyncpg_pool()).acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO booking (
                        buyer_id, event_id, section, subsection, quantity,
                        total_price, seat_selection_mode, seat_positions, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id, buyer_id, event_id, section, subsection, quantity,
                              total_price, seat_selection_mode, seat_positions, status,
                              created_at, updated_at, paid_at
                    """,
                    booking.buyer_id,
                    booking.event_id,
                    booking.section,
                    booking.subsection,
                    booking.quantity,
                    booking.total_price,
                    booking.seat_selection_mode,
                    booking.seat_positions,
                    booking.status.value,
                )

                created_booking = self._row_to_entity(row)
                if created_booking.id is not None:
                    span.set_attribute('booking.id', created_booking.id)
                return created_booking

    @Logger.io
    async def update_status_to_pending_payment(self, *, booking: Booking) -> Booking:
        async with (await get_asyncpg_pool()).acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE booking
                SET status = $1,
                    total_price = $2,
                    seat_positions = $3,
                    updated_at = $4
                WHERE id = $5
                RETURNING id, buyer_id, event_id, section, subsection, quantity,
                          total_price, seat_selection_mode, seat_positions, status,
                          created_at, updated_at, paid_at
                """,
                booking.status.value,
                booking.total_price,
                booking.seat_positions,
                booking.updated_at,
                booking.id,
            )

            if not row:
                raise ValueError(f'Booking with id {booking.id} not found')

            return self._row_to_entity(row)

    @Logger.io
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        async with (await get_asyncpg_pool()).acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE booking
                SET status = $1,
                    updated_at = $2
                WHERE id = $3
                RETURNING id, buyer_id, event_id, section, subsection, quantity,
                          total_price, seat_selection_mode, seat_positions, status,
                          created_at, updated_at, paid_at
                """,
                booking.status.value,
                booking.updated_at,
                booking.id,
            )

            if not row:
                raise ValueError(f'Booking with id {booking.id} not found')

            return self._row_to_entity(row)

    @Logger.io
    async def update_status_to_failed(self, *, booking: Booking) -> Booking:
        async with (await get_asyncpg_pool()).acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE booking
                SET status = $1,
                    updated_at = $2
                WHERE id = $3
                RETURNING id, buyer_id, event_id, section, subsection, quantity,
                          total_price, seat_selection_mode, seat_positions, status,
                          created_at, updated_at, paid_at
                """,
                booking.status.value,
                booking.updated_at,
                booking.id,
            )

            if not row:
                raise ValueError(f'Booking with id {booking.id} not found')

            return self._row_to_entity(row)

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
                booking.id,
            )

            if not booking_row:
                raise ValueError(f'Booking with id {booking.id} not found')

            Logger.base.info(
                f'💳 [ATOMIC_PAY] Updated booking {booking.id} to COMPLETED and {len(ticket_ids)} tickets to SOLD'
            )

            return self._row_to_entity(booking_row)

    @Logger.io
    async def reserve_tickets_and_update_booking_atomically(
        self,
        *,
        booking_id: int,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_identifiers: list[str],
    ) -> tuple[Booking, List[TicketRef], int]:
        """
        Atomically reserve tickets and update booking using CTE with idempotency check.

        Idempotency: If booking status is not 'processing', returns existing data (likely duplicate event).

        Single SQL statement performs:
        1. Validate booking exists, buyer owns it, and check status
        2. Update tickets to RESERVED status with buyer_id (only if status = 'processing')
        3. Calculate total price from updated tickets
        4. Update booking to PENDING_PAYMENT with total_price and seat_positions

        Performance: 1 database round-trip vs 5 separate queries.
        """
        now = datetime.now(timezone.utc)

        async with (await get_asyncpg_pool()).acquire() as conn:
            # First check booking status for idempotency
            booking_check = await conn.fetchrow(
                """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at
                FROM booking
                WHERE id = $1 AND buyer_id = $2
                """,
                booking_id,
                buyer_id,
            )

            if not booking_check:
                raise ValueError(f'Booking {booking_id} not found or buyer mismatch')

            # Idempotency check: if not PROCESSING, this is likely a duplicate event
            if booking_check['status'] != 'processing':
                Logger.base.warning(
                    f'⚠️  [IDEMPOTENCY] Booking {booking_id} status is {booking_check["status"]}, '
                    f'not "processing" - skipping update (likely duplicate Kafka event)'
                )
                # Return existing booking and tickets
                existing_booking = self._row_to_entity(booking_check)
                existing_tickets = await self.get_tickets_by_booking_id(booking_id=booking_id)
                return (existing_booking, existing_tickets, booking_check['total_price'])

            # Debug: Check ticket availability before atomic update
            debug_tickets = await conn.fetch(
                """
                SELECT row_number, seat_number, status, buyer_id
                FROM ticket
                WHERE event_id = $1 AND section = $2 AND subsection = $3
                  AND (row_number || '-' || seat_number) = ANY($4::text[])
                LIMIT 5
                """,
                event_id,
                section,
                subsection,
                seat_identifiers,
            )
            if debug_tickets:
                Logger.base.info(
                    f'🔍 [DEBUG] Found {len(debug_tickets)} matching tickets before update: '
                    f'{[(t["row_number"], t["seat_number"], t["status"], t["buyer_id"]) for t in debug_tickets]}'
                )
            else:
                Logger.base.warning(
                    f'⚠️ [DEBUG] No matching tickets found for seat_identifiers={seat_identifiers} '
                    f'(event={event_id}, section={section}, subsection={subsection})'
                )

            # Status is PROCESSING - proceed with atomic update
            result = await conn.fetch(
                """
                WITH validated_booking AS (
                    -- Step 1: Verify booking exists and buyer owns it (already validated above)
                    SELECT id, buyer_id, event_id, section, subsection, quantity,
                           total_price, seat_selection_mode, seat_positions, status,
                           created_at, updated_at, paid_at
                    FROM booking
                    WHERE id = $1 AND buyer_id = $2 AND status = 'processing'
                ),
                updated_tickets AS (
                    -- Step 2: Reserve tickets and calculate price
                    UPDATE ticket
                    SET status = 'reserved',
                        buyer_id = $2,
                        updated_at = $3,
                        reserved_at = $3
                    WHERE event_id = $4
                      AND section = $5
                      AND subsection = $6
                      AND (row_number || '-' || seat_number) = ANY($7::text[])
                      AND status = 'available'
                    RETURNING id, event_id, section, subsection, row_number, seat_number,
                              price, status, buyer_id, created_at, updated_at, reserved_at
                ),
                price_calculation AS (
                    -- Step 3: Calculate total price from reserved tickets
                    SELECT COALESCE(SUM(price), 0) as total_price,
                           COUNT(*) as ticket_count
                    FROM updated_tickets
                ),
                updated_booking AS (
                    -- Step 4: Update booking with calculated price and seat positions
                    UPDATE booking
                    SET status = 'pending_payment',
                        total_price = (SELECT total_price FROM price_calculation),
                        seat_positions = $7,
                        updated_at = $3
                    WHERE id = $1
                      AND EXISTS (SELECT 1 FROM validated_booking)
                    RETURNING id, buyer_id, event_id, section, subsection, quantity,
                              total_price, seat_selection_mode, seat_positions, status,
                              created_at, updated_at, paid_at
                )
                -- Return both booking and tickets info
                SELECT
                    'booking' as type,
                    b.id, b.buyer_id, b.event_id, b.section, b.subsection, b.quantity,
                    b.total_price, b.seat_selection_mode, b.seat_positions, b.status,
                    b.created_at, b.updated_at, b.paid_at,
                    NULL::int as ticket_id, NULL::int as row_number, NULL::int as seat_number,
                    NULL::int as price, NULL::text as ticket_status, NULL::timestamp as reserved_at,
                    (SELECT ticket_count FROM price_calculation) as ticket_count
                FROM updated_booking b
                UNION ALL
                SELECT
                    'ticket' as type,
                    NULL, NULL, t.event_id, t.section, t.subsection, NULL,
                    NULL, NULL, NULL, NULL,
                    NULL, NULL, NULL,
                    t.id, t.row_number, t.seat_number,
                    t.price, t.status, t.reserved_at,
                    NULL
                FROM updated_tickets t
                """,
                booking_id,
                buyer_id,
                now,
                event_id,
                section,
                subsection,
                seat_identifiers,
            )

            if not result:
                raise ValueError(f'Booking {booking_id} not found or buyer mismatch')

            # Separate booking and ticket rows
            booking_row = None
            ticket_rows = []
            ticket_count = 0

            for row in result:
                if row['type'] == 'booking':
                    booking_row = row
                    ticket_count = row['ticket_count'] or 0
                else:
                    ticket_rows.append(row)

            if not booking_row:
                raise ValueError(f'Failed to update booking {booking_id}')

            # Verify ticket count matches
            if ticket_count != len(seat_identifiers):
                Logger.base.warning(
                    f'⚠️ [ATOMIC] Ticket count mismatch: found {ticket_count} available tickets for {len(seat_identifiers)} seat identifiers '
                    f'(booking_id={booking_id}, section={section}, subsection={subsection}). '
                    f'This usually means tickets were already reserved (idempotency) or not available.'
                )
                raise ValueError(
                    f'Found {ticket_count} available tickets for {len(seat_identifiers)} seat identifiers'
                )

            # Convert to entities
            updated_booking = self._row_to_entity(booking_row)
            total_price = booking_row['total_price']

            reserved_tickets = []
            for row in ticket_rows:
                ticket = TicketRef(
                    event_id=row['event_id'],
                    section=row['section'],
                    subsection=row['subsection'],
                    row=row['row_number'],
                    seat=row['seat_number'],
                    price=row['price'],
                    status=TicketStatus(row['ticket_status']),
                    buyer_id=buyer_id,
                    id=row['ticket_id'],
                    created_at=row['created_at'],
                    updated_at=now,
                    reserved_at=row['reserved_at'],
                )
                reserved_tickets.append(ticket)

            Logger.base.info(
                f'🚀 [ATOMIC] Reserved {len(reserved_tickets)} tickets and updated booking {booking_id} '
                f'to PENDING_PAYMENT (total: {total_price}) in 1 DB round-trip'
            )

            return (updated_booking, reserved_tickets, total_price)

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List[TicketRef]:
        """
        查詢 booking 關聯的 tickets（用於 command 操作）

        Uses booking's event_id, section, subsection, and seat_positions to find matching tickets
        via the unique constraint (event_id, section, subsection, row_number, seat_number)

        Args:
            booking_id: Booking ID

        Returns:
            List of ticket references with full details
        """
        async with (await get_asyncpg_pool()).acquire() as conn:
            # First, get booking info
            booking_row = await conn.fetchrow(
                """
                SELECT event_id, section, subsection, seat_positions
                FROM booking
                WHERE id = $1
                """,
                booking_id,
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
                  AND (t.row_number || '-' || t.seat_number) = ANY($4::text[])
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
                    status=row['status'],
                    id=row['id'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                )
                tickets.append(ticket)

            return tickets
