"""
Event Ticketing Command Repository - ScyllaDB Implementation
"""

import asyncio
from datetime import datetime, timezone
import json
from typing import List, Optional

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    IEventTicketingCommandRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
)
from src.service.ticketing.domain.enum.ticket_status import TicketStatus


class EventTicketingCommandRepoScyllaImpl(IEventTicketingCommandRepo):
    """
    ScyllaDB implementation of Event Ticketing Command Repository

    Uses ScyllaDB with:
    - events table: Stores event information
    - tickets table: Stores tickets with composite partition key (event_id, section, subsection)
    """

    def __init__(self):
        pass

    @Logger.io
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """Create Event Aggregate (包含 Event 和 Tickets)"""
        session = await get_scylla_session()

        # Use provided ID or generate new one (timestamp-based, production should use Snowflake)
        event_id = event_aggregate.event.id or int(datetime.now(timezone.utc).timestamp() * 1000000)
        now = datetime.now(timezone.utc)

        # Fetch seller_name for denormalization
        seller_query = 'SELECT name FROM "user" WHERE id = %s'
        seller_result = await asyncio.to_thread(
            session.execute, seller_query, (event_aggregate.event.seller_id,)
        )
        seller_row = seller_result.one()
        seller_name = seller_row.name if seller_row else 'Unknown Seller'

        # Insert event
        event_query = """
            INSERT INTO "event" (
                id, name, description, seller_id, seller_name,
                is_active, status, venue_name, seating_config
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        await asyncio.to_thread(
            session.execute,
            event_query,
            (
                event_id,
                event_aggregate.event.name,
                event_aggregate.event.description,
                event_aggregate.event.seller_id,
                seller_name,  # seller_name - fetched from user table for denormalization
                event_aggregate.event.is_active,
                event_aggregate.event.status.value,
                event_aggregate.event.venue_name,
                json.dumps(event_aggregate.event.seating_config),
            ),
        )

        # Update aggregate with generated ID
        event_aggregate.event.id = event_id
        event_aggregate.event.created_at = now

        # Insert tickets if any
        if event_aggregate.tickets:
            await self._batch_insert_tickets(session, event_aggregate.tickets)

        return event_aggregate

    @Logger.io
    async def create_event_aggregate_with_batch_tickets(
        self,
        *,
        event_aggregate: EventTicketingAggregate,
        ticket_tuples: Optional[List[tuple]] = None,
    ) -> EventTicketingAggregate:
        """Create Event Aggregate with batch tickets"""
        session = await get_scylla_session()

        if not event_aggregate.event.id:
            raise ValueError('Event must have ID for batch ticket creation')

        # Use provided tuples or generate from tickets
        if ticket_tuples:
            # Batch insert using tuples format: (event_id, section, subsection, row, seat, price, status)
            ticket_query = """
                INSERT INTO "ticket" (
                    event_id, section, subsection, row_number, seat_number,
                    id, price, status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            now = datetime.now(timezone.utc)

            # Execute in batches to avoid overwhelming the cluster
            batch_size = 1000
            for i in range(0, len(ticket_tuples), batch_size):
                batch = ticket_tuples[i : i + batch_size]

                # Use concurrent.futures for parallel execution
                from cassandra.concurrent import execute_concurrent_with_args

                # Generate ticket IDs and prepare statements
                statements_and_params = []
                for event_id, section, subsection, row, seat, price, status in batch:
                    ticket_id = int(datetime.now(timezone.utc).timestamp() * 1000000) + i
                    statements_and_params.append(
                        (
                            event_id,
                            section,
                            subsection,
                            row,
                            seat,
                            ticket_id,
                            price,
                            status,
                            now,
                        )
                    )

                await asyncio.to_thread(
                    execute_concurrent_with_args,
                    session,
                    ticket_query,
                    statements_and_params,
                )

                Logger.base.info(f'Inserted batch {i // batch_size + 1} ({len(batch)} tickets)')

        elif event_aggregate.tickets:
            await self._batch_insert_tickets(session, event_aggregate.tickets)

        return event_aggregate

    async def _batch_insert_tickets(self, session, tickets: List[Ticket]) -> None:
        """Helper method to batch insert tickets"""
        if not tickets:
            return

        ticket_query = """
            INSERT INTO "ticket" (
                event_id, section, subsection, row_number, seat_number,
                id, price, status, buyer_id, reserved_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        now = datetime.now(timezone.utc)

        # Generate IDs for tickets and prepare batch
        statements_and_params = []
        for idx, ticket in enumerate(tickets):
            if not ticket.id:
                ticket.id = int(datetime.now(timezone.utc).timestamp() * 1000000) + idx
                ticket.created_at = now

            statements_and_params.append(
                (
                    ticket.event_id,
                    ticket.section,
                    ticket.subsection,
                    ticket.row,
                    ticket.seat,
                    ticket.id,
                    ticket.price,
                    ticket.status.value
                    if isinstance(ticket.status, TicketStatus)
                    else ticket.status,
                    ticket.buyer_id,
                    ticket.reserved_at,
                    ticket.created_at,
                    ticket.updated_at,
                )
            )

        # Execute batch
        from cassandra.concurrent import execute_concurrent_with_args

        batch_size = 1000
        for i in range(0, len(statements_and_params), batch_size):
            batch = statements_and_params[i : i + batch_size]
            await asyncio.to_thread(execute_concurrent_with_args, session, ticket_query, batch)

        Logger.base.info(f'Inserted {len(tickets)} tickets')

    @Logger.io
    async def update_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """Update Event Aggregate"""
        session = await get_scylla_session()

        if not event_aggregate.event.id:
            raise ValueError('Event must have ID to update')

        now = datetime.now(timezone.utc)

        update_query = """
            UPDATE "event"
            SET name = %s, description = %s, is_active = %s,
                status = %s, venue_name = %s, seating_config = %s
            WHERE id = %s
        """

        await asyncio.to_thread(
            session.execute,
            update_query,
            (
                event_aggregate.event.name,
                event_aggregate.event.description,
                event_aggregate.event.is_active,
                event_aggregate.event.status.value,
                event_aggregate.event.venue_name,
                json.dumps(event_aggregate.event.seating_config),
                event_aggregate.event.id,
            ),
        )

        event_aggregate.event.updated_at = now

        return event_aggregate

    @Logger.io
    async def update_tickets_status(
        self, *, ticket_ids: List[int], status: TicketStatus, buyer_id: Optional[int] = None
    ) -> List[Ticket]:
        """Update tickets status"""
        session = await get_scylla_session()

        now = datetime.now(timezone.utc)

        # First, fetch tickets to get their partition keys (event_id, section, subsection)
        # ScyllaDB requires partition key for UPDATE
        select_query = """
            SELECT event_id, section, subsection, row_number, seat_number, id, price, status, buyer_id, reserved_at, created_at, updated_at
            FROM "ticket"
            WHERE id IN %s
            ALLOW FILTERING
        """

        result = await asyncio.to_thread(session.execute, select_query, (tuple(ticket_ids),))
        rows = result.all()

        if not rows:
            return []

        # Update each ticket (ScyllaDB requires full partition key)
        update_query = """
            UPDATE "ticket"
            SET status = %s, buyer_id = %s, reserved_at = %s, updated_at = %s
            WHERE event_id = %s AND section = %s AND subsection = %s AND row_number = %s AND seat_number = %s
        """

        updated_tickets = []
        reserved_at = now if status == TicketStatus.RESERVED else None

        for row in rows:
            await asyncio.to_thread(
                session.execute,
                update_query,
                (
                    status.value,
                    buyer_id,
                    reserved_at,
                    now,
                    row.event_id,
                    row.section,
                    row.subsection,
                    row.row_number,
                    row.seat_number,
                ),
            )

            # Construct updated ticket
            ticket = Ticket(
                id=row.id,
                event_id=row.event_id,
                section=row.section,
                subsection=row.subsection,
                row=row.row_number,
                seat=row.seat_number,
                price=row.price,
                status=status,
                buyer_id=buyer_id,
                reserved_at=reserved_at,
                created_at=row.created_at,
                updated_at=now,
            )
            updated_tickets.append(ticket)

        Logger.base.info(f'Updated {len(updated_tickets)} tickets to status {status.value}')

        return updated_tickets

    @Logger.io
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """Delete Event Aggregate (cascade delete tickets)"""
        session = await get_scylla_session()

        # Delete tickets first (get partition keys)
        select_tickets_query = """
            SELECT event_id, section, subsection, row_number, seat_number
            FROM "ticket"
            WHERE event_id = %s
            ALLOW FILTERING
        """

        result = await asyncio.to_thread(session.execute, select_tickets_query, (event_id,))
        ticket_rows = result.all()

        # Delete each ticket
        delete_ticket_query = """
            DELETE FROM "ticket"
            WHERE event_id = %s AND section = %s AND subsection = %s AND row_number = %s AND seat_number = %s
        """

        for row in ticket_rows:
            await asyncio.to_thread(
                session.execute,
                delete_ticket_query,
                (row.event_id, row.section, row.subsection, row.row_number, row.seat_number),
            )

        # Delete event
        delete_event_query = 'DELETE FROM "event" WHERE id = %s'
        await asyncio.to_thread(session.execute, delete_event_query, (event_id,))

        Logger.base.info(f'Deleted event {event_id} and {len(ticket_rows)} tickets')

        return True
