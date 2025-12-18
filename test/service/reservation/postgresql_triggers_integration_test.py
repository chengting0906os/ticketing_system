"""
Integration tests for PostgreSQL Triggers on event statistics.

Tests verify that:
1. Triggers fire on ticket INSERT/UPDATE
2. event.stats and subsection_stats table are correctly maintained
3. Differential (+/-) updates work correctly
4. Idempotency is guaranteed
5. total = available + reserved + sold (regression test for bug fix)
"""

import json
from collections.abc import AsyncGenerator

import pytest

from src.platform.database.asyncpg_setting import get_asyncpg_pool


@pytest.fixture
async def test_user() -> AsyncGenerator[int, None]:
    """Create a test user for foreign key constraint"""
    pool = await get_asyncpg_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            """
            INSERT INTO "user" (name, email, hashed_password, role, is_active, is_superuser, is_verified)
            VALUES ('Test Seller', 'test_seller@example.com', 'hashed_password', 'seller', true, false, true)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """
        )

    yield user_id


@pytest.fixture
async def test_event(test_user: int) -> AsyncGenerator[int, None]:
    """
    Create a test event and automatically cleanup after test.

    Yields:
        event_id: The created event's ID
    """
    pool = await get_asyncpg_pool()
    async with pool.acquire() as conn:
        event_id = await conn.fetchval(
            """
            INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
            VALUES ('Test Event', 'Test', $1, true, 'available', 'Test Venue', '{}')
            RETURNING id
            """,
            test_user,
        )

    yield event_id

    # Automatic cleanup after test
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
        await conn.execute('DELETE FROM event WHERE id = $1', event_id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestPostgreSQLTriggersWithBatchInsert:
    """Test that PostgreSQL triggers work with batch ticket insertion"""

    async def test_batch_insert_tickets_initializes_stats_via_triggers(
        self, test_user: int
    ) -> None:
        """Test that batch INSERT of tickets triggers stats initialization"""
        pool = await get_asyncpg_pool()

        async with pool.acquire() as conn:
            # Given: Create event with seating config
            event_id = await conn.fetchval(
                """
                INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
                VALUES ('Batch Insert Test Event', 'Test', $1, true, 'available', 'Test Venue', $2::jsonb)
                RETURNING id
                """,
                test_user,
                json.dumps(
                    {
                        'rows': 2,
                        'cols': 3,
                        'sections': [
                            {'name': 'A', 'price': 1000, 'subsections': 1},
                            {'name': 'B', 'price': 1500, 'subsections': 2},
                        ],
                    }
                ),
            )

            # When: Batch insert tickets
            # Section A: 2 rows × 3 cols × 1 subsection = 6 seats
            for row in range(1, 3):  # 2 rows
                for seat in range(1, 4):  # 3 seats
                    await conn.execute(
                        """
                        INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                        VALUES ($1, 'A', 1, $2, $3, 1000, 'available')
                        """,
                        event_id,
                        row,
                        seat,
                    )

            # Section B: 2 rows × 3 cols × 2 subsections = 12 seats
            for subsection in range(1, 3):  # 2 subsections
                for row in range(1, 3):  # 2 rows
                    for seat in range(1, 4):  # 3 seats
                        await conn.execute(
                            """
                            INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                            VALUES ($1, 'B', $2, $3, $4, 1500, 'available')
                            """,
                            event_id,
                            subsection,
                            row,
                            seat,
                        )

            # Then: Verify stats are initialized correctly
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats

            # Total: 6 (A) + 12 (B) = 18 seats
            assert stats_dict['available'] == 18
            assert stats_dict['reserved'] == 0
            assert stats_dict['sold'] == 0

            # Check subsection_stats table
            subsection_stats = await conn.fetch(
                'SELECT section, subsection, available, reserved, sold FROM subsection_stats WHERE event_id = $1 ORDER BY section, subsection',
                event_id,
            )

            # Should have 3 subsections: A-1, B-1, B-2
            assert len(subsection_stats) == 3

            # Section A, Subsection 1 (6 seats)
            assert subsection_stats[0]['section'] == 'A'
            assert subsection_stats[0]['subsection'] == 1
            assert subsection_stats[0]['available'] == 6
            assert subsection_stats[0]['reserved'] == 0
            assert subsection_stats[0]['sold'] == 0

            # Section B, Subsection 1 (6 seats)
            assert subsection_stats[1]['section'] == 'B'
            assert subsection_stats[1]['subsection'] == 1
            assert subsection_stats[1]['available'] == 6
            assert subsection_stats[1]['reserved'] == 0
            assert subsection_stats[1]['sold'] == 0

            # Section B, Subsection 2 (6 seats)
            assert subsection_stats[2]['section'] == 'B'
            assert subsection_stats[2]['subsection'] == 2
            assert subsection_stats[2]['available'] == 6
            assert subsection_stats[2]['reserved'] == 0
            assert subsection_stats[2]['sold'] == 0

            # Cleanup
            await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
            await conn.execute('DELETE FROM event WHERE id = $1', event_id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestPostgreSQLTriggersDifferentialUpdates:
    """Test PostgreSQL triggers with differential (+/-) updates"""

    async def test_trigger_updates_stats_on_status_change(self, test_event: int) -> None:
        """Test that changing ticket status updates stats correctly"""
        pool = await get_asyncpg_pool()
        event_id = test_event

        async with pool.acquire() as conn:
            # Given: Insert 3 tickets with status 'available'
            for i in range(1, 4):
                await conn.execute(
                    """
                    INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                    VALUES ($1, 'A', 1, 1, $2, 1000, 'available')
                    """,
                    event_id,
                    i,
                )

            # Check initial stats
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats
            assert stats_dict['available'] == 3
            assert stats_dict['reserved'] == 0

            # When: Update 1 ticket from 'available' to 'reserved'
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'reserved'
                WHERE event_id = $1 AND section = 'A' AND subsection = 1 AND row_number = 1 AND seat_number = 1
                """,
                event_id,
            )

            # Then: Stats should be updated (available-1, reserved+1)
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats
            assert stats_dict['available'] == 2  # 3 - 1
            assert stats_dict['reserved'] == 1  # 0 + 1

            # Check subsection_stats table
            subsection_stats = await conn.fetchrow(
                "SELECT available, reserved, sold FROM subsection_stats WHERE event_id = $1 AND section = 'A' AND subsection = 1",
                event_id,
            )
            assert subsection_stats['available'] == 2
            assert subsection_stats['reserved'] == 1
            assert subsection_stats['sold'] == 0

    async def test_trigger_idempotency_same_status_update(self, test_event: int) -> None:
        """Test that updating to same status doesn't change stats (idempotency)"""
        pool = await get_asyncpg_pool()
        event_id = test_event

        async with pool.acquire() as conn:
            # Given: Insert ticket
            await conn.execute(
                """
                INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                VALUES ($1, 'A', 1, 1, 1, 1000, 'available')
                """,
                event_id,
            )

            # Get initial stats
            initial_stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            initial_dict = (
                json.loads(initial_stats) if isinstance(initial_stats, str) else initial_stats
            )

            # When: Update ticket to same status (available -> available)
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'available'
                WHERE event_id = $1 AND section = 'A' AND subsection = 1 AND row_number = 1 AND seat_number = 1
                """,
                event_id,
            )

            # Then: Stats should NOT change
            updated_stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            updated_dict = (
                json.loads(updated_stats) if isinstance(updated_stats, str) else updated_stats
            )

            assert updated_dict['available'] == initial_dict['available']
            assert updated_dict['reserved'] == initial_dict['reserved']

    async def test_trigger_handles_full_ticket_lifecycle(self, test_event: int) -> None:
        """Test full lifecycle: available -> reserved -> sold"""
        pool = await get_asyncpg_pool()
        event_id = test_event

        async with pool.acquire() as conn:
            # Given: Insert ticket
            await conn.execute(
                """
                INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                VALUES ($1, 'A', 1, 1, 1, 1000, 'available')
                """,
                event_id,
            )

            # Step 1: available -> reserved
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'reserved'
                WHERE event_id = $1 AND section = 'A' AND subsection = 1 AND row_number = 1 AND seat_number = 1
                """,
                event_id,
            )

            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats
            assert stats_dict['available'] == 0
            assert stats_dict['reserved'] == 1
            assert stats_dict['sold'] == 0

            # Step 2: reserved -> sold
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'sold'
                WHERE event_id = $1 AND section = 'A' AND subsection = 1 AND row_number = 1 AND seat_number = 1
                """,
                event_id,
            )

            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats
            assert stats_dict['available'] == 0
            assert stats_dict['reserved'] == 0
            assert stats_dict['sold'] == 1

            # Verify subsection_stats table
            subsection_stats = await conn.fetchrow(
                "SELECT available, reserved, sold FROM subsection_stats WHERE event_id = $1 AND section = 'A' AND subsection = 1",
                event_id,
            )
            assert subsection_stats['available'] == 0
            assert subsection_stats['reserved'] == 0
            assert subsection_stats['sold'] == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestTotalFieldMaintenance:
    """Test that event.stats.total is correctly maintained by triggers"""

    async def test_total_equals_sum_of_statuses(self, test_event: int) -> None:
        """Test that total = available + reserved + sold"""
        pool = await get_asyncpg_pool()
        event_id = test_event

        async with pool.acquire() as conn:
            # Given: Insert 10 available tickets
            for i in range(1, 11):
                await conn.execute(
                    """
                    INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                    VALUES ($1, 'A', 1, 1, $2, 1000, 'available')
                    """,
                    event_id,
                    i,
                )

            # Update 3 tickets to reserved
            await conn.execute(
                """
                UPDATE ticket SET status = 'reserved'
                WHERE event_id = $1 AND seat_number IN (1, 2, 3)
                """,
                event_id,
            )

            # Update 2 tickets to sold
            await conn.execute(
                """
                UPDATE ticket SET status = 'sold'
                WHERE event_id = $1 AND seat_number IN (4, 5)
                """,
                event_id,
            )

            # Then: Verify total = available + reserved + sold
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats

            # available: 10 - 3 - 2 = 5, reserved: 3, sold: 2, total: 10
            assert stats_dict['available'] == 5
            assert stats_dict['reserved'] == 3
            assert stats_dict['sold'] == 2
            assert stats_dict['total'] == 10

    async def test_total_unchanged_through_status_transitions(self, test_event: int) -> None:
        """Test that total remains unchanged when ticket status changes"""
        pool = await get_asyncpg_pool()
        event_id = test_event

        async with pool.acquire() as conn:
            # Given: Insert 3 available tickets
            for i in range(1, 4):
                await conn.execute(
                    """
                    INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                    VALUES ($1, 'A', 1, 1, $2, 1000, 'available')
                    """,
                    event_id,
                    i,
                )

            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            initial_total = (json.loads(stats) if isinstance(stats, str) else stats)['total']

            # When: available -> reserved -> sold
            await conn.execute(
                "UPDATE ticket SET status = 'reserved' WHERE event_id = $1 AND seat_number = 1",
                event_id,
            )
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            total_after_reserved = (json.loads(stats) if isinstance(stats, str) else stats)['total']

            await conn.execute(
                "UPDATE ticket SET status = 'sold' WHERE event_id = $1 AND seat_number = 1",
                event_id,
            )
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            total_after_sold = (json.loads(stats) if isinstance(stats, str) else stats)['total']

            # Then: Total should remain unchanged
            assert total_after_reserved == initial_total
            assert total_after_sold == initial_total

    async def test_total_consistency_with_mass_reservations(self, test_user: int) -> None:
        """Test total field consistency with 2000 tickets (bug regression test)"""
        pool = await get_asyncpg_pool()

        async with pool.acquire() as conn:
            # Given: Create event with 2000 tickets
            event_id = await conn.fetchval(
                """
                INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
                VALUES ('Mass Reservation Test', 'Test', $1, true, 'available', 'Test Venue', '{}')
                RETURNING id
                """,
                test_user,
            )

            # Insert 2000 tickets (40 rows × 50 seats)
            for row in range(1, 41):
                for seat in range(1, 51):
                    await conn.execute(
                        """
                        INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                        VALUES ($1, 'A', 1, $2, $3, 1000, 'available')
                        """,
                        event_id,
                        row,
                        seat,
                    )

            # Reserve all 2000 tickets
            await conn.execute(
                "UPDATE ticket SET status = 'reserved' WHERE event_id = $1",
                event_id,
            )

            # Then: Verify stats (this was a bug - total was showing 0)
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats

            assert stats_dict['available'] == 0
            assert stats_dict['reserved'] == 2000
            assert stats_dict['sold'] == 0
            assert stats_dict['total'] == 2000

            # Cleanup (not using fixture since we need custom event)
            await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
            await conn.execute('DELETE FROM event WHERE id = $1', event_id)
