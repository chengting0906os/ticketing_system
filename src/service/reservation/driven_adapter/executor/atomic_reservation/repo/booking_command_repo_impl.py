"""
Booking Command Repository Implementation (for Reservation Service)

Writes booking data to PostgreSQL after successful Kvrocks reservation.
"""

from datetime import datetime, timezone
from typing import Union

from opentelemetry import trace
from uuid_utils import UUID

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.interface.i_booking_command_repo import (
    IBookingCommandRepo,
)
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class BookingCommandRepoImpl(IBookingCommandRepo):
    """
    Booking Command Repository for Reservation Service

    Handles PostgreSQL writes for booking and ticket data.
    Called after successful Kvrocks atomic reservation.
    """

    def __init__(self) -> None:
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def create_booking_with_tickets_directly(
        self,
        *,
        booking_id: Union[str, UUID],
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
        Uses CTE to atomically create booking and update tickets in single query.
        """
        with self.tracer.start_as_current_span(
            'reservation.repo.create_booking_with_tickets',
            attributes={
                'booking.id': str(booking_id),
                'event.id': event_id,
                'buyer.id': buyer_id,
                'seat.section': section,
                'seat.subsection': subsection,
                'seats.count': len(reserved_seats),
                'booking.total_price': total_price,
                'db.system': 'postgresql',
                'db.operation': 'insert',
            },
        ):
            now = datetime.now(timezone.utc)

            async with (await get_asyncpg_pool()).acquire() as conn:
                booking_uuid = UUID(booking_id) if isinstance(booking_id, str) else booking_id

                # Check if booking already exists (idempotency)
                existing = await conn.fetchrow(
                    'SELECT id FROM booking WHERE id = $1',
                    booking_uuid,
                )

                if existing:
                    Logger.base.warning(
                        f'⚠️ [IDEMPOTENCY] Booking {booking_id} already exists - skipping'
                    )
                    return {'booking': None, 'tickets': [], 'already_exists': True}

                # Use CTE to atomically create booking and update tickets
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
                          AND (row_number || '-' || seat_number) = ANY($9::text[])
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

                created_booking = Booking(
                    buyer_id=booking_row['buyer_id'],
                    event_id=booking_row['event_id'],
                    section=booking_row['section'],
                    subsection=booking_row['subsection'],
                    quantity=booking_row['quantity'],
                    total_price=booking_row['total_price'],
                    seat_selection_mode=booking_row['seat_selection_mode'] or 'manual',
                    seat_positions=booking_row['seat_positions'] or [],
                    status=BookingStatus(booking_row['status']),
                    id=UUID(str(booking_row['id'])),
                    created_at=booking_row['created_at'],
                    updated_at=booking_row['updated_at'],
                    paid_at=booking_row['paid_at'],
                )

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

                Logger.base.info(
                    f'✅ [RESERVATION→PG] Created booking {booking_id} in PENDING_PAYMENT '
                    f'with {len(tickets)} RESERVED tickets (total: {total_price})'
                )

                return {
                    'booking': created_booking,
                    'tickets': tickets,
                }

    @Logger.io
    async def create_failed_booking_directly(
        self,
        *,
        booking_id: Union[str, UUID],
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
        Called when seat reservation fails.
        """
        with self.tracer.start_as_current_span(
            'reservation.repo.create_failed_booking',
            attributes={
                'booking.id': str(booking_id),
                'event.id': event_id,
                'buyer.id': buyer_id,
                'booking.status': 'failed',
                'db.system': 'postgresql',
                'db.operation': 'insert',
            },
        ):
            now = datetime.now(timezone.utc)

            async with (await get_asyncpg_pool()).acquire() as conn:
                booking_uuid = UUID(booking_id) if isinstance(booking_id, str) else booking_id

                # Check if booking already exists (idempotency)
                existing = await conn.fetchrow(
                    'SELECT id, status FROM booking WHERE id = $1',
                    booking_uuid,
                )

                if existing:
                    Logger.base.warning(
                        f'⚠️ [IDEMPOTENCY] Booking {booking_id} already exists with status {existing["status"]}'
                    )
                    # Return a minimal booking object for idempotency
                    return Booking(
                        buyer_id=buyer_id,
                        event_id=event_id,
                        section=section,
                        subsection=subsection,
                        quantity=quantity,
                        total_price=0,
                        seat_selection_mode=seat_selection_mode,
                        seat_positions=seat_positions,
                        status=BookingStatus(existing['status']),
                        id=booking_uuid,
                        created_at=now,
                        updated_at=now,
                    )

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

                created_booking = Booking(
                    buyer_id=booking_row['buyer_id'],
                    event_id=booking_row['event_id'],
                    section=booking_row['section'],
                    subsection=booking_row['subsection'],
                    quantity=booking_row['quantity'],
                    total_price=booking_row['total_price'],
                    seat_selection_mode=booking_row['seat_selection_mode'] or 'manual',
                    seat_positions=booking_row['seat_positions'] or [],
                    status=BookingStatus(booking_row['status']),
                    id=UUID(str(booking_row['id'])),
                    created_at=booking_row['created_at'],
                    updated_at=booking_row['updated_at'],
                    paid_at=booking_row['paid_at'],
                )

                Logger.base.info(
                    f'✅ [RESERVATION→PG] Created booking {booking_id} in FAILED status '
                    f'(requested {quantity} seats in {section}-{subsection})'
                )

                return created_booking
