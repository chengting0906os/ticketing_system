"""
Integration test for event.stats.total field maintenance via PostgreSQL Triggers.

Verifies that:
1. total = available + reserved + sold
2. total increases on INSERT
3. total remains unchanged on status UPDATE
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
            VALUES ('Test Seller', 'test_total_field@example.com', 'hashed_password', 'seller', true, false, true)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """
        )

    yield user_id


@pytest.mark.integration
@pytest.mark.asyncio
class TestTotalFieldMaintenance:
    """Test that event.stats.total is correctly maintained by triggers"""

    async def test_total_equals_sum_of_statuses(self, test_user: int) -> None:
        """Test that total = available + reserved + sold"""
        pool = await get_asyncpg_pool()

        async with pool.acquire() as conn:
            # Given: Create event and tickets with different statuses
            event_id = await conn.fetchval(
                """
                INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
                VALUES ('Total Field Test', 'Test', $1, true, 'available', 'Test Venue', '{}')
                RETURNING id
                """,
                test_user,
            )

            # Insert 10 available tickets
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
                UPDATE ticket
                SET status = 'reserved'
                WHERE event_id = $1 AND seat_number IN (1, 2, 3)
                """,
                event_id,
            )

            # Update 2 tickets to sold
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'sold'
                WHERE event_id = $1 AND seat_number IN (4, 5)
                """,
                event_id,
            )

            # Then: Verify total = available + reserved + sold
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats

            # available: 10 - 3 - 2 = 5
            # reserved: 3
            # sold: 2
            # total: 5 + 3 + 2 = 10
            assert stats_dict['available'] == 5
            assert stats_dict['reserved'] == 3
            assert stats_dict['sold'] == 2
            assert stats_dict['total'] == 10

            # Cleanup
            await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
            await conn.execute('DELETE FROM event WHERE id = $1', event_id)

    async def test_total_increases_on_insert(self, test_user: int) -> None:
        """Test that total increases when tickets are inserted"""
        pool = await get_asyncpg_pool()

        async with pool.acquire() as conn:
            # Given: Create event
            event_id = await conn.fetchval(
                """
                INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
                VALUES ('Insert Test', 'Test', $1, true, 'available', 'Test Venue', '{}')
                RETURNING id
                """,
                test_user,
            )

            # Initially stats might be None if no tickets inserted yet
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            if stats is None:
                initial_total = 0
            else:
                stats_dict = json.loads(stats) if isinstance(stats, str) else stats
                initial_total = stats_dict.get('total', 0)

            # When: Insert 5 tickets
            for i in range(1, 6):
                await conn.execute(
                    """
                    INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                    VALUES ($1, 'A', 1, 1, $2, 1000, 'available')
                    """,
                    event_id,
                    i,
                )

            # Then: Total should increase by 5
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats

            assert stats_dict['total'] == initial_total + 5
            assert stats_dict['available'] == 5

            # Cleanup
            await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
            await conn.execute('DELETE FROM event WHERE id = $1', event_id)

    async def test_total_unchanged_on_status_update(self, test_user: int) -> None:
        """Test that total remains unchanged when ticket status changes"""
        pool = await get_asyncpg_pool()

        async with pool.acquire() as conn:
            # Given: Create event with tickets
            event_id = await conn.fetchval(
                """
                INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
                VALUES ('Status Update Test', 'Test', $1, true, 'available', 'Test Venue', '{}')
                RETURNING id
                """,
                test_user,
            )

            # Insert 3 available tickets
            for i in range(1, 4):
                await conn.execute(
                    """
                    INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                    VALUES ($1, 'A', 1, 1, $2, 1000, 'available')
                    """,
                    event_id,
                    i,
                )

            # Get initial total
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            initial_total = (json.loads(stats) if isinstance(stats, str) else stats)['total']

            # When: Change status available -> reserved -> sold
            # available -> reserved
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'reserved'
                WHERE event_id = $1 AND seat_number = 1
                """,
                event_id,
            )

            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            total_after_reserved = (json.loads(stats) if isinstance(stats, str) else stats)['total']

            # reserved -> sold
            await conn.execute(
                """
                UPDATE ticket
                SET status = 'sold'
                WHERE event_id = $1 AND seat_number = 1
                """,
                event_id,
            )

            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            total_after_sold = (json.loads(stats) if isinstance(stats, str) else stats)['total']

            # Then: Total should remain unchanged
            assert total_after_reserved == initial_total
            assert total_after_sold == initial_total

            # Cleanup
            await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
            await conn.execute('DELETE FROM event WHERE id = $1', event_id)

    async def test_total_consistency_with_mass_reservations(self, test_user: int) -> None:
        """Test total field consistency during realistic reservation scenario"""
        pool = await get_asyncpg_pool()

        async with pool.acquire() as conn:
            # Given: Create event with 2000 tickets (simulating actual data)
            event_id = await conn.fetchval(
                """
                INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
                VALUES ('Mass Reservation Test', 'Test', $1, true, 'available', 'Test Venue', '{}')
                RETURNING id
                """,
                test_user,
            )

            # Insert 2000 available tickets
            for row in range(1, 41):  # 40 rows
                for seat in range(1, 51):  # 50 seats per row
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
                """
                UPDATE ticket
                SET status = 'reserved'
                WHERE event_id = $1
                """,
                event_id,
            )

            # Then: Verify stats match scenario
            stats = await conn.fetchval('SELECT stats FROM event WHERE id = $1', event_id)
            stats_dict = json.loads(stats) if isinstance(stats, str) else stats

            # Should match observed data structure
            assert stats_dict['available'] == 0
            assert stats_dict['reserved'] == 2000
            assert stats_dict['sold'] == 0
            assert stats_dict['total'] == 2000  # ✅ This was the bug - was showing 0

            # Cleanup
            await conn.execute('DELETE FROM ticket WHERE event_id = $1', event_id)
            await conn.execute('DELETE FROM event WHERE id = $1', event_id)
