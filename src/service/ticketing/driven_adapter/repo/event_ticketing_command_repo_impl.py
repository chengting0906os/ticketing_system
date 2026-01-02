"""
Event Ticketing Command Repository Implementation - CQRS Write Side (Raw SQL with asyncpg)

Unified event ticketing command repository implementation
Uses EventTicketingAggregate as the unit of operation to ensure aggregate consistency

Performance: Using raw SQL with asyncpg for maximum performance
"""

import time
from typing import List

import orjson

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    IEventTicketingCommandRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
)


class EventTicketingCommandRepoImpl(IEventTicketingCommandRepo):
    """Event Ticketing Command Repository Implementation (Raw SQL with asyncpg)"""

    def __init__(self) -> None:
        pass  # No session needed for raw SQL approach

    @Logger.io
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """Create Event Aggregate (including Event and Tickets)"""
        async with (await get_asyncpg_pool()).acquire() as conn, conn.transaction():
            # 1. Save Event
            event_row = await conn.fetchrow(
                """
                    INSERT INTO event (
                        name, description, seller_id, venue_name,
                        seating_config, is_active, status
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                    RETURNING id, name, description, seller_id, venue_name,
                              seating_config, is_active, status
                    """,
                event_aggregate.event.name,
                event_aggregate.event.description,
                event_aggregate.event.seller_id,
                event_aggregate.event.venue_name,
                orjson.dumps(event_aggregate.event.seating_config).decode(),
                event_aggregate.event.is_active,
                event_aggregate.event.status.value,
            )

            # 2. Update Event entity ID
            event_aggregate.event.id = event_row['id']

            # 3. Save Tickets (if any)
            if event_aggregate.tickets:
                ticket_records = [
                    (
                        event_row['id'],
                        ticket.section,
                        ticket.subsection,
                        ticket.row,
                        ticket.seat,
                        ticket.price,
                        ticket.status.value,
                        ticket.buyer_id,
                        ticket.reserved_at,
                    )
                    for ticket in event_aggregate.tickets
                ]

                await conn.executemany(
                    """
                        INSERT INTO ticket (
                            event_id, section, subsection, row_number, seat_number,
                            price, status, buyer_id, reserved_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                    ticket_records,
                )

                # Get inserted ticket IDs
                ticket_rows = await conn.fetch(
                    """
                        SELECT id, event_id, section, subsection, row_number, seat_number,
                               price, status, buyer_id, reserved_at, created_at, updated_at
                        FROM ticket
                        WHERE event_id = $1
                        ORDER BY id
                        """,
                    event_row['id'],
                )

                # Update Ticket entity IDs
                for i, ticket_row in enumerate(ticket_rows):
                    if i < len(event_aggregate.tickets):
                        event_aggregate.tickets[i].id = ticket_row['id']

            Logger.base.info(
                f'🗾 [CREATE_AGGREGATE] Created event {event_row["id"]} with {len(event_aggregate.tickets)} tickets'
            )

            return event_aggregate

    @Logger.io
    async def create_event_aggregate_with_batch_tickets(
        self,
        *,
        event_aggregate: EventTicketingAggregate,
        ticket_tuples: List[tuple],
    ) -> EventTicketingAggregate:
        """Create Event Aggregate using high-performance batch ticket creation

        Note: This method assumes Event already exists and has an ID.
        Only batch creates tickets, does not recreate event.

        Performance optimization: Temporarily disables trigger during batch insert
        and manually calculates stats to avoid 50k+ trigger executions.
        Triggers are for normal ticketing operations, not initialization.
        """
        # Check if Event already has an ID (already persisted)
        if not event_aggregate.event.id:
            raise ValueError('Event must be persisted before using batch ticket creation')

        start_time = time.time()
        actual_tuples = ticket_tuples

        # Use asyncpg connection pool for COPY operation
        async with (await get_asyncpg_pool()).acquire() as conn:
            async with conn.transaction():
                # Temporarily disable trigger to avoid overhead during batch insert
                await conn.execute(
                    'ALTER TABLE ticket DISABLE TRIGGER ticket_status_change_trigger'
                )

                # COPY operation
                copy_start = time.time()
                await conn.copy_records_to_table(
                    'ticket',
                    records=actual_tuples,
                    columns=[
                        'event_id',
                        'section',
                        'subsection',
                        'row_number',
                        'seat_number',
                        'price',
                        'status',
                    ],
                    timeout=120.0,
                )
                copy_time = time.time() - copy_start
                Logger.base.info(f'  📦 [BATCH_CREATE] COPY completed ({copy_time:.3f}s)')

                # Re-enable trigger
                await conn.execute('ALTER TABLE ticket ENABLE TRIGGER ticket_status_change_trigger')

                # Directly calculate and insert stats based on inserted tickets
                stats_start = time.time()

                # Calculate event-level stats
                event_stats = await conn.fetchrow(
                    """
                    SELECT 
                        COALESCE(SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END), 0) AS available,
                        COALESCE(SUM(CASE WHEN status = 'reserved' THEN 1 ELSE 0 END), 0) AS reserved,
                        COALESCE(SUM(CASE WHEN status = 'sold' THEN 1 ELSE 0 END), 0) AS sold,
                        COALESCE(COUNT(*), 0) AS total
                    FROM ticket
                    WHERE event_id = $1
                    """,
                    event_aggregate.event.id,
                )

                # Update event.stats
                await conn.execute(
                    """
                    UPDATE event
                    SET stats = jsonb_build_object(
                        'available', $2::int,
                        'reserved', $3::int,
                        'sold', $4::int,
                        'total', $5::int,
                        'updated_at', EXTRACT(EPOCH FROM NOW())::bigint
                    )
                    WHERE id = $1
                    """,
                    event_aggregate.event.id,
                    event_stats['available'],
                    event_stats['reserved'],
                    event_stats['sold'],
                    event_stats['total'],
                )

                # Calculate and insert subsection-level stats
                await conn.execute(
                    """
                    INSERT INTO subsection_stats (event_id, section, subsection, price, available, reserved, sold, updated_at)
                    SELECT
                        t.event_id,
                        t.section,
                        t.subsection,
                        MAX(t.price) AS price,
                        SUM(CASE WHEN t.status = 'available' THEN 1 ELSE 0 END) AS available,
                        SUM(CASE WHEN t.status = 'reserved' THEN 1 ELSE 0 END) AS reserved,
                        SUM(CASE WHEN t.status = 'sold' THEN 1 ELSE 0 END) AS sold,
                        EXTRACT(EPOCH FROM NOW())::bigint AS updated_at
                    FROM ticket t
                    WHERE t.event_id = $1
                    GROUP BY t.event_id, t.section, t.subsection
                    ON CONFLICT (event_id, section, subsection) DO UPDATE
                    SET
                        available = EXCLUDED.available,
                        reserved = EXCLUDED.reserved,
                        sold = EXCLUDED.sold,
                        updated_at = EXCLUDED.updated_at
                    """,
                    event_aggregate.event.id,
                )

                # Update aggregate's event.stats
                event_aggregate.event.stats = dict(event_stats)

                stats_time = time.time() - stats_start
                Logger.base.info(
                    f'  📊 [BATCH_CREATE] Stats calculation completed ({stats_time:.3f}s)'
                )

            # Fetch inserted tickets (outside transaction for better performance)
            fetch_start = time.time()
            rows = await conn.fetch(
                """
                SELECT id, event_id, section, subsection, row_number, seat_number, price, status,
                        buyer_id, reserved_at, created_at, updated_at
                FROM ticket
                WHERE event_id = $1
                ORDER BY id
            """,
                event_aggregate.event.id,
            )
            fetch_time = time.time() - fetch_start
            Logger.base.info(f'  🔍 [BATCH_CREATE] Fetch completed ({fetch_time:.3f}s)')

            # Update Ticket entity IDs
            convert_start = time.time()
            for i, row in enumerate(rows):
                if i < len(event_aggregate.tickets):
                    event_aggregate.tickets[i].id = row['id']

            convert_time = time.time() - convert_start
            total_time = time.time() - start_time

            Logger.base.info(
                f'🎯 [BATCH_CREATE] Completed! {len(event_aggregate.tickets):,} tickets in {total_time:.3f}s'
            )
            Logger.base.info(
                f'📊 [BATCH_CREATE] Performance: {len(event_aggregate.tickets) / total_time:.0f} tickets/sec'
            )
            Logger.base.info(
                f'⚡ [BATCH_CREATE] Breakdown: COPY={copy_time:.3f}s, Stats={stats_time:.3f}s, Fetch={fetch_time:.3f}s, Convert={convert_time:.3f}s'
            )

        return event_aggregate

    @Logger.io
    async def update_event_status(self, *, event_id: int, status: str) -> None:
        """Update Event status only (without updating tickets)."""
        async with (await get_asyncpg_pool()).acquire() as conn:
            await conn.execute(
                """
                UPDATE event
                SET status = $1
                WHERE id = $2
                """,
                status,
                event_id,
            )
            Logger.base.info(f'🔄 [UPDATE_STATUS] Updated event {event_id} status to {status}')

    @Logger.io
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """
        Delete Event Aggregate (cascade delete tickets)

        Used for compensating transactions when Kvrocks initialization fails.
        """
        async with (await get_asyncpg_pool()).acquire() as conn:
            try:
                async with conn.transaction():
                    # First delete tickets
                    tickets_result = await conn.execute(
                        """
                        DELETE FROM ticket
                        WHERE event_id = $1
                        """,
                        event_id,
                    )

                    # Then delete event
                    event_result = await conn.execute(
                        """
                        DELETE FROM event
                        WHERE id = $1
                        """,
                        event_id,
                    )

                    # Parse deleted row count (format: "DELETE n")
                    tickets_count = int(tickets_result.split()[-1]) if tickets_result else 0
                    event_count = int(event_result.split()[-1]) if event_result else 0

                    success = event_count > 0
                    Logger.base.info(
                        f'🗑️ [DELETE_AGGREGATE] Deleted event {event_id}: '
                        f'{tickets_count} tickets, {event_count} event'
                    )
                    return success

            except Exception as e:
                Logger.base.error(f'❌ [DELETE_AGGREGATE] Failed to delete event {event_id}: {e}')
                return False
