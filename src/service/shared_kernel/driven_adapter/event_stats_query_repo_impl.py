"""
Event Stats Query Repository Implementation

Queries event and subsection stats from PostgreSQL.
Used by throttled broadcast mechanism.
"""

import orjson

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger


class EventStatsQueryRepoImpl:
    """Query repository for event stats from PostgreSQL"""

    async def get_event_stats(self, event_id: int) -> dict:
        """
        Query event and subsection stats from PostgreSQL.

        Args:
            event_id: Event ID

        Returns:
            Dict with event_stats and subsection_stats
        """
        pool = await get_asyncpg_pool()
        async with pool.acquire() as conn:
            # Query event.stats JSONB
            event_row = await conn.fetchrow(
                'SELECT stats FROM event WHERE id = $1',
                event_id,
            )
            event_stats = {}
            if event_row and event_row['stats']:
                stats = event_row['stats']
                # Handle case where stats is a JSON string instead of dict
                if isinstance(stats, str):
                    stats = orjson.loads(stats)
                event_stats = {
                    'available': stats.get('available', 0),
                    'reserved': stats.get('reserved', 0),
                    'sold': stats.get('sold', 0),
                    'total': stats.get('total', 0),
                    'updated_at': stats.get('updated_at', 0),
                }

            # Query subsection_stats (all for this event)
            subsection_rows = await conn.fetch(
                """
                SELECT section, subsection, price, available, reserved, sold, updated_at
                FROM subsection_stats
                WHERE event_id = $1
                ORDER BY section, subsection
                """,
                event_id,
            )
            subsection_stats = [
                {
                    'section': row['section'],
                    'subsection': row['subsection'],
                    'price': row['price'],
                    'available': row['available'],
                    'reserved': row['reserved'],
                    'sold': row['sold'],
                    'updated_at': row['updated_at'],
                }
                for row in subsection_rows
            ]

            Logger.base.debug(f'📊 [StatsQuery] Queried stats for event={event_id}')

            return {
                'event_stats': event_stats,
                'subsection_stats': subsection_stats,
            }
