#!/usr/bin/env python3
"""
Database Seed Script
Populate test data into the database

Features:
1. Create Users - Create 3 test users (1 seller + 1 buyer + 1 load test)
2. Create Event - Create event and send seat initialization to Kafka (→ reservation Kvrocks)

Notes:
- Seat data is stored in reservation's Kvrocks (not PostgreSQL)
- Ticket data is stored in event_ticketing's PostgreSQL
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from src.platform.config.di import container
from src.platform.database.db_setting import async_session_maker
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.driven_adapter.repo.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.service.ticketing.driven_adapter.repo.user_command_repo_impl import UserCommandRepoImpl
from src.service.ticketing.driven_adapter.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)

DEFAULT_PASSWORD = 'P@ssw0rd'
CONFIG_FILE = Path(__file__).parent / 'seating_config.json'


@dataclass
class UserConfig:
    """User seed configuration"""
    email: str
    name: str
    role: UserRole


# Test users to create
TEST_USERS = [
    UserConfig(email='s@t.com', name='init seller', role=UserRole.SELLER),
    UserConfig(email='b@t.com', name='init buyer', role=UserRole.BUYER),
    UserConfig(email='b_1@t.com', name='Load Test User', role=UserRole.BUYER),
]


def _load_seating_config() -> tuple[dict, int]:
    """
    Load seating configuration based on SEATS environment variable.

    Returns:
        tuple: (config dict, total_seats count)
    """
    seats = os.getenv('SEATS', '500')

    with open(CONFIG_FILE, 'r') as f:
        all_configs = json.load(f)

    if seats not in all_configs:
        print(f'⚠️  Seats config {seats} not found, using 500')
        seats = '500'

    config = all_configs[seats]
    rows = config.get('rows', 1)
    cols = config.get('cols', 10)

    total_seats = sum(
        section.get('subsections', 1) * rows * cols
        for section in config['sections']
    )

    print(f'📊 Using seating config: {seats} ({total_seats:,} seats)')
    return config, total_seats


async def _create_user(user_repo, password_hasher, config: UserConfig) -> UserEntity:
    """Create a single user"""
    user = UserEntity(
        email=config.email,
        name=config.name,
        role=config.role,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    user.set_password(DEFAULT_PASSWORD, password_hasher)
    return await user_repo.create(user)


async def create_users(session) -> int:
    """Create initial test users

    Returns:
        int: seller_id
    """
    print(f'👥 Creating {len(TEST_USERS)} users...')

    @asynccontextmanager
    async def get_session():
        yield session

    user_repo = UserCommandRepoImpl(lambda: get_session())
    password_hasher = BcryptPasswordHasher()

    seller_id = None

    for config in TEST_USERS:
        created_user = await _create_user(user_repo, password_hasher, config)
        role_label = 'seller' if config.role == UserRole.SELLER else 'buyer'
        print(f'   ✅ Created {role_label}: ID={created_user.id}, Email={created_user.email}')

        if config.role == UserRole.SELLER:
            seller_id = created_user.id

    if seller_id is None:
        raise Exception("Failed to create seller: ID is None")

    print(f'   📧 Credentials: {DEFAULT_PASSWORD}')
    return seller_id


async def create_event(session, seller_id: int):
    """Create initial test event"""
    print('🎫 Creating initial event...')

    # Verify seller exists
    result = await session.execute(
        text(f'SELECT id, email FROM "user" WHERE id = {seller_id}')
    )
    user_check = result.fetchone()

    if not user_check:
        print(f'   ❌ Seller {seller_id} NOT found in database!')
        return None

    print(f'   🔍 Seller found: ID={user_check[0]}, Email={user_check[1]}')

    # Get dependencies from DI container
    event_ticketing_repo = EventTicketingCommandRepoImpl()
    init_state_handler = container.init_event_and_tickets_state_handler()
    mq_infra_orchestrator = container.mq_infra_orchestrator()

    create_event_use_case = CreateEventAndTicketsUseCase(
        event_ticketing_command_repo=event_ticketing_repo,
        mq_infra_orchestrator=mq_infra_orchestrator,
        init_state_handler=init_state_handler,
    )

    seating_config, _ = _load_seating_config()

    event_aggregate = await create_event_use_case.create_event_and_tickets(
        name='Concert Event',
        description='Amazing live music performance',
        seller_id=seller_id,
        venue_name='Taipei Arena',
        seating_config=seating_config,
        is_active=True,
    )

    event = event_aggregate.event
    tickets = event_aggregate.tickets

    print(f'   ✅ Created event: ID={event.id}, Name={event.name}')
    print(f'   ✅ Created tickets: {len(tickets)}')
    return event.id


async def verify_data():
    """Verify seeded data"""
    print('🔍 Verifying seeded data...')

    async with async_session_maker()() as session:
        # Count records
        for table in ['user', 'event', 'ticket']:
            table_name = f'"{table}"' if table == 'user' else table
            result = await session.execute(text(f'SELECT COUNT(*) FROM {table_name}'))
            count = result.scalar()
            print(f'   {table.capitalize()} count: {count}')

        # List users
        result = await session.execute(
            text('SELECT id, email, role FROM "user" ORDER BY id')
        )
        for user in result.fetchall():
            print(f'      User ID={user[0]}, Email={user[1]}, Role={user[2]}')

        # List events
        result = await session.execute(
            text('SELECT id, name, seller_id FROM event')
        )
        for event in result.fetchall():
            print(f'      Event ID={event[0]}, Name={event[1]}, Seller={event[2]}')

    print('   ✅ Data verification completed!')


async def _initialize_kvrocks():
    """Initialize Kvrocks connection"""
    try:
        await kvrocks_client.initialize()
        print('📡 Kvrocks connection pool initialized')
    except Exception as e:
        print(f'❌ Failed to initialize Kvrocks: {e}')
        raise


async def _seed_data():
    """Seed users and event in a single transaction"""
    async with async_session_maker()() as session:
        try:
            seller_id = await create_users(session)
            print()

            await create_event(session, seller_id)
            print()

            await session.commit()
            print('✅ All data committed successfully!')

        except Exception as e:
            await session.rollback()
            print(f'❌ Rolling back: {e}')
            raise


async def main():
    print('🌱 Starting data seeding...')
    print('=' * 50)

    try:
        await _initialize_kvrocks()
        await _seed_data()
        await verify_data()

        print()
        print('=' * 50)
        print('🌱 Data seeding completed!')
        print('📋 Test accounts:')
        for user in TEST_USERS:
            role = 'Seller' if user.role == UserRole.SELLER else 'Buyer'
            print(f'   {role}: {user.email} / {DEFAULT_PASSWORD}')

    except Exception as e:
        print(f'❌ Seeding failed: {e}')
        exit(1)

    finally:
        try:
            await kvrocks_client.disconnect()
            print('📡 Kvrocks connection closed')
        except Exception:
            pass


if __name__ == '__main__':
    asyncio.run(main())
