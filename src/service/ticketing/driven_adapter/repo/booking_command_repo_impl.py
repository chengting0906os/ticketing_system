"""
Booking Command Repository Implementation (Ticketing Service)

Provides read and payment operations for bookings.
Note: Booking creation and cancellation are handled by Reservation Service.
"""

from datetime import datetime, timezone
from typing import List

import asyncpg
from uuid_utils import UUID

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class BookingCommandRepoImpl(IBookingCommandRepo):
    """
    Booking Command Repository (Ticketing Service)

    Responsibilities:
    - Read booking for validation
    - Payment completion (PENDING_PAYMENT → COMPLETED)

    Note: Booking creation and cancellation are handled by Reservation Service.
    """

    @staticmethod
    def _row_to_entity(row: asyncpg.Record) -> Booking:
        """Convert asyncpg Record to Booking entity"""
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
            id=UUID(str(row['id'])),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            paid_at=row['paid_at'],
        )

    @Logger.io
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        """Query single booking (used for validation before command operations)"""
        async with (await get_asyncpg_pool()).acquire() as conn:
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
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List[TicketRef]:
        """
        Query tickets associated with booking (used for command operations)

        Uses booking's event_id, section, subsection, and seat_positions to find matching tickets
        via the unique constraint (event_id, section, subsection, row_number, seat_number)
        """
        async with (await get_asyncpg_pool()).acquire() as conn:
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
                    status=TicketStatus(row['status']),
                    id=row['id'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                )
                tickets.append(ticket)

            return tickets

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
        """
        now = datetime.now(timezone.utc)

        async with (await get_asyncpg_pool()).acquire() as conn:
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
