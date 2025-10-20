from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

from opentelemetry import trace

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
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
