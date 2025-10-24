"""
Event Ticketing Query Repository - ScyllaDB Implementation
"""

import asyncio
import json
from typing import List, Optional

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    Event,
    EventTicketingAggregate,
    Ticket,
)
from src.service.ticketing.domain.enum.event_status import EventStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus


class EventTicketingQueryRepoScyllaImpl(IEventTicketingQueryRepo):
    """
    ScyllaDB implementation of Event Ticketing Query Repository

    Optimized for read performance:
    - Leverages ScyllaDB's secondary indexes
    - Uses partition-aware queries when possible
    - Avoids ALLOW FILTERING when using indexed columns
    """

    def __init__(self):
        pass

    @Logger.io
    async def get_event_aggregate_by_id_with_tickets(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        """Get Event Aggregate by ID with tickets"""
        session = await get_scylla_session()

        # Fetch event
        event_query = 'SELECT * FROM "event" WHERE id = %s'
        event_result = await asyncio.to_thread(session.execute, event_query, (event_id,))
        event_row = event_result.one()

        if not event_row:
            return None

        # Fetch all tickets for the event
        tickets_query = """
            SELECT * FROM "ticket"
            WHERE event_id = %s
            ALLOW FILTERING
        """
        tickets_result = await asyncio.to_thread(session.execute, tickets_query, (event_id,))
        ticket_rows = tickets_result.all()

        # Build aggregate
        event = self._row_to_event(event_row)
        tickets = [self._row_to_ticket(row) for row in ticket_rows]

        return EventTicketingAggregate(event=event, tickets=tickets)

    @Logger.io
    async def list_events_by_seller(self, *, seller_id: int) -> List[EventTicketingAggregate]:
        """List events by seller"""
        session = await get_scylla_session()

        # Use seller_id index
        query = """
            SELECT * FROM "event"
            WHERE seller_id = %s
        """
        result = await asyncio.to_thread(session.execute, query, (seller_id,))
        rows = result.all()

        # Return events without tickets (performance optimization)
        aggregates = []
        for row in rows:
            event = self._row_to_event(row)
            aggregates.append(EventTicketingAggregate(event=event, tickets=[]))

        return aggregates

    @Logger.io
    async def list_available_events(self) -> List[EventTicketingAggregate]:
        """List available events"""
        session = await get_scylla_session()

        # Full table scan - consider adding status index in production
        query = """
            SELECT * FROM "event"
            WHERE is_active = true
            ALLOW FILTERING
        """
        result = await asyncio.to_thread(session.execute, query)
        rows = result.all()

        # Return events without tickets (performance optimization)
        aggregates = []
        for row in rows:
            event = self._row_to_event(row)
            if event.status in [EventStatus.AVAILABLE, EventStatus.DRAFT]:
                aggregates.append(EventTicketingAggregate(event=event, tickets=[]))

        return aggregates

    @Logger.io
    async def get_tickets_by_event_and_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """Get tickets by event and section"""
        session = await get_scylla_session()

        # Efficient query using partition key
        query = """
            SELECT * FROM "ticket"
            WHERE event_id = %s AND section = %s AND subsection = %s
        """
        result = await asyncio.to_thread(session.execute, query, (event_id, section, subsection))
        rows = result.all()

        return [self._row_to_ticket(row) for row in rows]

    @Logger.io
    async def get_available_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """Get available tickets by event"""
        session = await get_scylla_session()

        query = """
            SELECT * FROM "ticket"
            WHERE event_id = %s
            ALLOW FILTERING
        """
        result = await asyncio.to_thread(session.execute, query, (event_id,))
        rows = result.all()

        # Filter by status
        tickets = [
            self._row_to_ticket(row) for row in rows if row.status == TicketStatus.AVAILABLE.value
        ]

        return tickets

    @Logger.io
    async def get_reserved_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """Get reserved tickets by event"""
        session = await get_scylla_session()

        query = """
            SELECT * FROM "ticket"
            WHERE event_id = %s
            ALLOW FILTERING
        """
        result = await asyncio.to_thread(session.execute, query, (event_id,))
        rows = result.all()

        # Filter by status
        tickets = [
            self._row_to_ticket(row) for row in rows if row.status == TicketStatus.RESERVED.value
        ]

        return tickets

    @Logger.io
    async def get_all_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """Get all tickets by event"""
        session = await get_scylla_session()

        query = """
            SELECT * FROM "ticket"
            WHERE event_id = %s
            ALLOW FILTERING
        """
        result = await asyncio.to_thread(session.execute, query, (event_id,))
        rows = result.all()

        return [self._row_to_ticket(row) for row in rows]

    @Logger.io
    async def get_tickets_by_buyer(self, *, buyer_id: int) -> List[Ticket]:
        """Get tickets by buyer"""
        session = await get_scylla_session()

        # Use buyer_id index
        query = """
            SELECT * FROM "ticket"
            WHERE buyer_id = %s
        """
        result = await asyncio.to_thread(session.execute, query, (buyer_id,))
        rows = result.all()

        return [self._row_to_ticket(row) for row in rows]

    @Logger.io
    async def get_tickets_by_ids(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """Get tickets by IDs"""
        session = await get_scylla_session()

        if not ticket_ids:
            return []

        # Query with IN clause (requires ALLOW FILTERING)
        query = """
            SELECT * FROM "ticket"
            WHERE id IN %s
            ALLOW FILTERING
        """
        result = await asyncio.to_thread(session.execute, query, (tuple(ticket_ids),))
        rows = result.all()

        return [self._row_to_ticket(row) for row in rows]

    @Logger.io
    async def check_tickets_exist_for_event(self, *, event_id: int) -> bool:
        """Check if tickets exist for event"""
        session = await get_scylla_session()

        # Use COUNT for existence check
        query = """
            SELECT COUNT(*) as count FROM "ticket"
            WHERE event_id = %s
            LIMIT 1
            ALLOW FILTERING
        """
        result = await asyncio.to_thread(session.execute, query, (event_id,))
        row = result.one()

        return row.count > 0 if row else False

    @staticmethod
    def _row_to_event(row) -> Event:
        """Convert database row to Event entity"""
        return Event(
            id=row.id,
            name=row.name,
            description=row.description,
            seller_id=row.seller_id,
            venue_name=row.venue_name,
            seating_config=json.loads(row.seating_config) if row.seating_config else {},
            is_active=row.is_active,
            status=EventStatus(row.status),
            created_at=row.created_at if hasattr(row, 'created_at') else None,
            updated_at=row.updated_at if hasattr(row, 'updated_at') else None,
        )

    @staticmethod
    def _row_to_ticket(row) -> Ticket:
        """Convert database row to Ticket entity"""
        return Ticket(
            id=row.id,
            event_id=row.event_id,
            section=row.section,
            subsection=row.subsection,
            row=row.row_number,
            seat=row.seat_number,
            price=row.price,
            status=TicketStatus(row.status),
            buyer_id=row.buyer_id,
            reserved_at=row.reserved_at if hasattr(row, 'reserved_at') else None,
            created_at=row.created_at if hasattr(row, 'created_at') else None,
            updated_at=row.updated_at if hasattr(row, 'updated_at') else None,
        )
