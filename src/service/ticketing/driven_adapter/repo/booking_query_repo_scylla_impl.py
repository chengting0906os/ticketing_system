import asyncio
from typing import List
from uuid import UUID

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class BookingQueryRepoScyllaImpl(IBookingQueryRepo):
    """
    ScyllaDB Booking Query Repository - Read-optimized with denormalized data

    No session_factory needed for ScyllaDB - uses global session pool
    Denormalized fields eliminate JOINs for fast reads
    """

    def __init__(self):
        pass

    @staticmethod
    def _to_entity(row) -> Booking:
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

    @staticmethod
    def _to_booking_dict(row) -> dict:
        """
        Convert Cassandra Row to booking dict with denormalized fields (for list view)

        ScyllaDB advantage: All fields already denormalized!
        Zero additional queries needed - everything in one row
        """
        return {
            'id': row.id,
            'buyer_id': row.buyer_id,
            'event_id': row.event_id,
            'total_price': row.total_price,
            'status': row.status,
            'created_at': row.created_at,
            'paid_at': row.paid_at,
            # Denormalized fields (already in ScyllaDB table)
            'event_name': getattr(row, 'event_name', 'Unknown Event'),
            'buyer_name': getattr(row, 'buyer_name', 'Unknown Buyer'),
            'seller_name': getattr(row, 'seller_name', 'Unknown Seller'),
            'venue_name': getattr(row, 'venue_name', 'Unknown Venue'),
            'section': row.section,
            'subsection': row.subsection,
            'quantity': row.quantity,
            'seat_selection_mode': row.seat_selection_mode or 'manual',
            'seat_positions': list(row.seat_positions) if row.seat_positions else [],
        }

    @staticmethod
    def _to_booking_detail_dict(row) -> dict:
        """
        Convert Cassandra Row to booking detail dict including tickets (for detail view)

        ScyllaDB advantage: All fields (including tickets) already denormalized!
        Zero additional queries needed - everything in one row
        """
        # Parse denormalized ticket data (already in the row)
        tickets_data = []
        if hasattr(row, 'tickets_data') and row.tickets_data:
            for ticket_map in row.tickets_data:
                # Handle ticket ID as UUID (string)
                ticket_id_str = ticket_map.get('id', '')
                from uuid import UUID

                ticket_id = UUID(ticket_id_str) if ticket_id_str else None

                tickets_data.append(
                    {
                        'id': ticket_id,
                        'section': ticket_map.get('section', ''),
                        'subsection': int(ticket_map.get('subsection', 0)),
                        'row': int(ticket_map.get('row', 0)),
                        'seat': int(ticket_map.get('seat', 0)),
                        'price': int(ticket_map.get('price', 0)),
                        'status': ticket_map.get('status', 'unknown'),
                    }
                )

        return {
            'id': row.id,
            'buyer_id': row.buyer_id,
            'event_id': row.event_id,
            'total_price': row.total_price,
            'status': row.status,
            'created_at': row.created_at,
            'paid_at': row.paid_at,
            # Denormalized fields (already in ScyllaDB table)
            'event_name': getattr(row, 'event_name', 'Unknown Event'),
            'buyer_name': getattr(row, 'buyer_name', 'Unknown Buyer'),
            'seller_name': getattr(row, 'seller_name', 'Unknown Seller'),
            'venue_name': getattr(row, 'venue_name', 'Unknown Venue'),
            'section': row.section,
            'subsection': row.subsection,
            'quantity': row.quantity,
            'seat_selection_mode': row.seat_selection_mode or 'manual',
            'seat_positions': list(row.seat_positions) if row.seat_positions else [],
            'tickets': tickets_data,  # Already denormalized - no separate query!
        }

    @Logger.io
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        """
        Get booking by ID

        Note: With PRIMARY KEY (buyer_id, id), we need ALLOW FILTERING for id-only queries
        This is acceptable for infrequent, single-row lookups
        """
        session = await get_scylla_session()

        query = """
            SELECT id, buyer_id, event_id, section, subsection, quantity,
                   total_price, seat_selection_mode, seat_positions, status,
                   created_at, updated_at, paid_at
            FROM "booking"
            WHERE id = %s
            ALLOW FILTERING
            """

        result = await asyncio.to_thread(session.execute, query, (booking_id,))
        row = result.one()

        if not row:
            return None

        return self._to_entity(row)

    @Logger.io
    async def get_by_id_with_details(self, *, booking_id: UUID) -> dict | None:
        """
        Get booking by ID with full details including tickets

        Note: With PRIMARY KEY (buyer_id, id), we need ALLOW FILTERING for id-only queries
        This is acceptable for detail views (infrequent, single-row lookup)

        ScyllaDB Optimization: All data (buyer, event, seller, tickets) denormalized in ONE row!
        Zero JOINs, zero N+1 queries
        """
        session = await get_scylla_session()

        query = """
            SELECT id, buyer_id, event_id, section, subsection, quantity,
                   total_price, seat_selection_mode, seat_positions, status,
                   created_at, updated_at, paid_at,
                   buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name,
                   tickets_data
            FROM "booking"
            WHERE id = %s
            ALLOW FILTERING
            """

        result = await asyncio.to_thread(session.execute, query, (booking_id,))
        row = result.one()

        if not row:
            return None

        # Everything in one row - no additional queries needed!
        return self._to_booking_detail_dict(row)

    @Logger.io
    async def get_buyer_bookings_with_details(self, *, buyer_id: UUID, status: str) -> List[dict]:
        """
        Get all bookings for a buyer with optional status filter

        ScyllaDB Optimization:
        - Direct partition key query (buyer_id) - FAST! No ALLOW FILTERING needed
        - Tickets already denormalized - no N+1 queries!
        - Returns bookings ordered by id DESC (latest first)
        """
        session = await get_scylla_session()

        # Build query with optional status filter
        if status:
            query = """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at,
                       buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name,
                       tickets_data
                FROM "booking"
                WHERE buyer_id = %s
                  AND status = %s
                ALLOW FILTERING
                """
            params = (buyer_id, status)
        else:
            # Direct partition key query - no ALLOW FILTERING needed!
            query = """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at,
                       buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name,
                       tickets_data
                FROM "booking"
                WHERE buyer_id = %s
                """
            params = (buyer_id,)

        result = await asyncio.to_thread(session.execute, query, params)
        rows = result.all()

        # Filter by status in Python if needed (more efficient than ALLOW FILTERING for small result sets)
        if status:
            rows = [row for row in rows if row.status == status]

        # Tickets already in each row - just parse and return!
        return [self._to_booking_dict(row) for row in rows]

    @Logger.io(truncate_content=True)  # type: ignore
    async def get_seller_bookings_with_details(self, *, seller_id: UUID, status: str) -> List[dict]:
        """
        Get all bookings for a seller's events with optional status filter

        ScyllaDB Optimization: Query bookings directly by seller_id!
        - seller_id denormalized in bookings table (no need to query events first)
        - tickets_data denormalized (no N+1 queries)
        - Single query instead of N+1!
        """
        session = await get_scylla_session()

        # Direct query by seller_id - no need to query events table!
        if status:
            query = """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at,
                       buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name,
                       tickets_data
                FROM "booking"
                WHERE seller_id = %s
                  AND status = %s
                ALLOW FILTERING
                """
            params = (seller_id, status)
        else:
            query = """
                SELECT id, buyer_id, event_id, section, subsection, quantity,
                       total_price, seat_selection_mode, seat_positions, status,
                       created_at, updated_at, paid_at,
                       buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name,
                       tickets_data
                FROM "booking"
                WHERE seller_id = %s
                ALLOW FILTERING
                """
            params = (seller_id,)

        result = await asyncio.to_thread(session.execute, query, params)
        rows = result.all()

        # Everything denormalized - single query, zero N+1!
        return [self._to_booking_dict(row) for row in rows]

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List[TicketRef]:
        """
        Get all tickets for a booking using seat_positions from booking

        Same implementation as command repo (reusable logic)
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

            result = await asyncio.to_thread(
                session.execute,
                query,
                (booking.event_id, booking.section, booking.subsection, row_num, seat_num),
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
