from datetime import datetime, timezone
from functools import partial
from typing import Any, List

import anyio.to_thread
from cassandra.query import BatchStatement, BatchType, SimpleStatement
from opentelemetry import trace

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class BookingCommandRepoScyllaImpl(IBookingCommandRepo):
    """
    ScyllaDB Booking Command Repository - Data Access Layer

    Architecture Rule: Repository NEVER commits!
    - Use case is responsible for transaction management (commit/rollback)
    - Repository only performs CRUD operations (add, update, flush)

    ScyllaDB Specifics:
    - No CTE support: Use BATCH with LWT (Lightweight Transactions) for atomicity
    - Denormalized data: Store buyer/event details for faster reads
    - LWT overhead: Use sparingly, only for critical atomic operations
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @staticmethod
    def _row_to_entity(row) -> Booking:
        """
        Convert Cassandra Row to Booking entity
        """
        return Booking(
            buyer_id=row.buyer_id,
            event_id=row.event_id,
            section=row.section,
            subsection=row.subsection,
            quantity=row.quantity,
            total_price=row.total_price,
            seat_selection_mode=row.seat_selection_mode or 'manual',
            seat_positions=list(row.seat_positions) if row.seat_positions else [],
            status=BookingStatus(row.status),
            id=row.id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            paid_at=row.paid_at,
        )

    @Logger.io
    async def get_by_id(self, *, booking_id: int) -> Booking | None:
        """查詢單筆 booking（用於 command 操作前的驗證）"""
        session = await get_scylla_session()

        query = """
            SELECT id, buyer_id, event_id, section, subsection, quantity,
                   total_price, seat_selection_mode, seat_positions, status,
                   created_at, updated_at, paid_at
            FROM "booking"
            WHERE id = %s
            """

        result = await anyio.to_thread.run_sync(partial(session.execute, query, (booking_id,)))
        row = result.one()

        if not row:
            return None

        return self._row_to_entity(row)

    async def create(self, *, booking: Booking) -> Booking:
        with self.tracer.start_as_current_span('db.booking.create') as span:
            session = await get_scylla_session()

            # Generate ID (in production, use distributed ID generator like Snowflake)
            booking_id = booking.id or int(datetime.now(timezone.utc).timestamp() * 1000000)
            now = datetime.now(timezone.utc)

            # Simplified insert - denormalized fields will be populated on first read
            query = """
                INSERT INTO "booking" (
                    id, buyer_id, event_id, section, subsection, quantity,
                    total_price, seat_selection_mode, seat_positions, status,
                    created_at, updated_at,
                    buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name,
                    tickets_data
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

            await anyio.to_thread.run_sync(
                partial(
                    session.execute,
                    query,
                    (
                        booking_id,
                        booking.buyer_id,
                        booking.event_id,
                        booking.section,
                        booking.subsection,
                        booking.quantity,
                        booking.total_price,
                        booking.seat_selection_mode,
                        booking.seat_positions,
                        booking.status.value,
                        now,
                        now,
                        None,  # buyer_name - lazy loaded on read
                        None,  # buyer_email - lazy loaded on read
                        None,  # event_name - lazy loaded on read
                        None,  # venue_name - lazy loaded on read
                        None,  # seller_id - lazy loaded on read
                        None,  # seller_name - lazy loaded on read
                        [],  # tickets_data initially empty
                    ),
                )
            )

            # Return booking with generated ID (avoid extra SELECT)
            booking.id = booking_id
            booking.created_at = now
            booking.updated_at = now

            span.set_attribute('booking.id', booking_id)
            return booking

    @Logger.io
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        session = await get_scylla_session()

        query = """
            UPDATE "booking"
            SET status = %s,
                updated_at = %s
            WHERE id = %s
            """

        await anyio.to_thread.run_sync(
            partial(
                session.execute,
                query,
                [
                    booking.status.value,
                    booking.updated_at,
                    booking.id,
                ],
            )
        )

        # Directly return the updated booking object (avoid extra SELECT)
        return booking

    @Logger.io
    async def update_status_to_failed(self, *, booking: Booking) -> Booking:
        session = await get_scylla_session()

        query = """
            UPDATE "booking"
            SET status = %s,
                updated_at = %s
            WHERE id = %s
            """

        await anyio.to_thread.run_sync(
            partial(
                session.execute,
                query,
                [
                    booking.status.value,
                    booking.updated_at,
                    booking.id,
                ],
            )
        )

        # Directly return the updated booking object (avoid extra SELECT)
        return booking

    @Logger.io
    async def complete_booking_and_mark_tickets_sold_atomically(
        self, *, booking: Booking, ticket_ids: list[int]
    ) -> Booking:
        """
        Atomically update booking to COMPLETED and mark tickets as SOLD using BATCH

        Also updates denormalized tickets_data in booking with 'sold' status
        """
        session = await get_scylla_session()
        now = datetime.now(timezone.utc)

        # Fetch tickets and prepare denormalized data
        tickets = await self.get_tickets_by_booking_id(booking_id=booking.id)  # type: ignore

        # Update tickets_data with 'sold' status
        tickets_data = [
            {
                'id': str(ticket.id),
                'section': ticket.section,
                'subsection': str(ticket.subsection),
                'row': str(ticket.row),
                'seat': str(ticket.seat),
                'price': str(ticket.price),
                'status': 'sold',  # Mark as sold
            }
            for ticket in tickets
        ]

        # Create BATCH statement (LOGGED for cross-partition atomicity)
        batch = BatchStatement(batch_type=BatchType.LOGGED)

        # Update booking with denormalized tickets_data
        batch.add(
            SimpleStatement("""
                UPDATE "booking"
                SET status = %s,
                    updated_at = %s,
                    paid_at = %s,
                    tickets_data = %s
                WHERE id = %s
                """),
            (booking.status.value, booking.updated_at, booking.paid_at, tickets_data, booking.id),
        )

        # Update tickets to SOLD
        for ticket in tickets:
            batch.add(
                SimpleStatement("""
                    UPDATE "ticket"
                    SET status = %s,
                        updated_at = %s
                    WHERE event_id = %s
                      AND section = %s
                      AND subsection = %s
                      AND row_number = %s
                      AND seat_number = %s
                    """),
                (
                    'sold',
                    now,
                    ticket.event_id,
                    ticket.section,
                    ticket.subsection,
                    ticket.row,
                    ticket.seat,
                ),
            )

        # Execute batch
        await anyio.to_thread.run_sync(partial(session.execute, batch))

        Logger.base.info(
            f'💳 [ATOMIC_PAY] Updated booking {booking.id} to COMPLETED '
            f'and {len(tickets)} tickets to SOLD (denormalized in booking)'
        )

        updated_booking = await self.get_by_id(booking_id=booking.id)  # type: ignore
        if not updated_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return updated_booking

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List[TicketRef]:
        """
        Get all tickets for a booking using seat_positions from booking

        Uses booking's event_id, section, subsection, and seat_positions to find matching tickets
        """
        session = await get_scylla_session()

        # First get booking info
        booking = await self.get_by_id(booking_id=booking_id)
        if not booking or not booking.seat_positions:
            return []

        tickets = []

        # Query each ticket by its composite partition key
        for seat_pos in booking.seat_positions:
            try:
                row_num, seat_num = seat_pos.split('-')
                row_num = int(row_num)
                seat_num = int(seat_num)
            except (ValueError, AttributeError):
                continue

            query = """
                SELECT id, event_id, section, subsection, row_number, seat_number,
                       price, status, buyer_id, reserved_at, created_at, updated_at
                FROM "ticket"
                WHERE event_id = %s
                  AND section = %s
                  AND subsection = %s
                  AND row_number = %s
                  AND seat_number = %s
                """

            result = await anyio.to_thread.run_sync(
                partial(
                    session.execute,
                    query,
                    (booking.event_id, booking.section, booking.subsection, row_num, seat_num),
                )
            )

            ticket_row = result.one()
            if ticket_row:
                ticket = TicketRef(
                    id=ticket_row.id,
                    event_id=ticket_row.event_id,
                    section=ticket_row.section,
                    subsection=ticket_row.subsection,
                    row=ticket_row.row_number,
                    seat=ticket_row.seat_number,
                    price=ticket_row.price,
                    status=TicketStatus(ticket_row.status),
                    buyer_id=ticket_row.buyer_id,
                    created_at=ticket_row.created_at,
                    updated_at=ticket_row.updated_at,
                    reserved_at=ticket_row.reserved_at,
                )
                tickets.append(ticket)

        return tickets

    # ==============================================================================
    #
    # Atomic Operations with LWT

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
        ticket_price: int,
    ) -> tuple[Booking, List[TicketRef], int]:
        """
        Update tickets to RESERVED and booking to PENDING_PAYMENT

        Atomicity Guarantee:
        - Kvrocks Lua script already ensured seat availability atomically
        - This method only persists the reservation to ScyllaDB
        - No LWT needed because Kvrocks is the source of truth

        Performance:
        - Uses ticket_price from Kvrocks to avoid N SELECT queries
        - Uses BATCH statement to reduce network round-trips from N+1 to 1
        - Single price value because all seats in same subsection have same price

        Args:
            booking_id: Booking ID
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section code
            subsection: Subsection number
            seat_identifiers: List of "row-seat" strings (e.g., ["1-1", "1-2"])
            ticket_price: Price per ticket from Kvrocks (same for all seats)

        Returns:
            Tuple of (updated_booking, reserved_tickets, total_price)
        """
        session = await get_scylla_session()
        now: datetime = datetime.now(timezone.utc)

        # Step 1: Build BATCH statement for all ticket updates + booking update (1 network round-trip)
        reserved_tickets: List[TicketRef] = []
        total_price = 0
        batch_statements: List[str] = []
        batch_params: List[Any] = []

        for seat_id in seat_identifiers:
            try:
                row_num, seat_num = seat_id.split('-')
                row_num = int(row_num)
                seat_num = int(seat_num)
            except (ValueError, AttributeError):
                Logger.base.error(f'❌ Invalid seat identifier: {seat_id}')
                continue

            # Use price from Kvrocks (all seats in same subsection have same price)
            price = ticket_price

            # Add ticket UPDATE to batch
            batch_statements.append(
                """
                UPDATE "ticket"
                SET status = %s,
                    buyer_id = %s,
                    updated_at = %s,
                    reserved_at = %s
                WHERE event_id = %s
                  AND section = %s
                  AND subsection = %s
                  AND row_number = %s
                  AND seat_number = %s
                """
            )
            batch_params.extend(
                ['reserved', buyer_id, now, now, event_id, section, subsection, row_num, seat_num]
            )

            # Create TicketRef without querying
            ticket = TicketRef(
                id=0,
                event_id=event_id,
                section=section,
                subsection=subsection,
                row=row_num,
                seat=seat_num,
                price=price,
                status=TicketStatus.RESERVED,
                buyer_id=buyer_id,
                created_at=now,
                updated_at=now,
                reserved_at=now,
            )
            reserved_tickets.append(ticket)
            total_price += price

        # Step 2: Add booking UPDATE to batch
        booking = Booking(
            id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            quantity=len(seat_identifiers),
            seat_selection_mode='manual',
            status=BookingStatus.PENDING_PAYMENT,
            total_price=total_price,
            seat_positions=seat_identifiers,
            updated_at=now,
        )

        # Convert reserved tickets to denormalized format
        tickets_data = [
            {
                'id': str(ticket.id),
                'section': ticket.section,
                'subsection': str(ticket.subsection),
                'row': str(ticket.row),
                'seat': str(ticket.seat),
                'price': str(ticket.price),
                'status': ticket.status.value,
            }
            for ticket in reserved_tickets
        ]

        # Add booking UPDATE to batch
        batch_statements.append(
            """
            UPDATE "booking"
            SET status = %s,
                total_price = %s,
                seat_positions = %s,
                tickets_data = %s,
                updated_at = %s
            WHERE id = %s
            """
        )
        batch_params.extend(
            [
                booking.status.value,
                booking.total_price,
                booking.seat_positions,
                tickets_data,
                booking.updated_at,
                booking.id,
            ]
        )

        # Step 3: Execute BATCH (1 network round-trip for all updates)
        batch_query = 'BEGIN BATCH\n' + ';\n'.join(batch_statements) + ';\nAPPLY BATCH'

        await anyio.to_thread.run_sync(partial(session.execute, batch_query, batch_params))

        Logger.base.info(
            f'🚀 [BATCH] Reserved {len(reserved_tickets)} tickets and updated booking {booking_id} '
            f'to PENDING_PAYMENT (total: {total_price}) in 1 network round-trip'
        )

        return (booking, reserved_tickets, total_price)
