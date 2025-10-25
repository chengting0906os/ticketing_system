#!/usr/bin/env python3
"""
Database Seed Script (ScyllaDB)
填充測試資料到資料庫

功能：
1. Create Users - 創建 3 個測試用戶 (1 seller + 1 buyer + 1 load test)
2. Create Event - 創建活動並發送座位初始化到 Kafka (→ seat_reservation Kvrocks)

注意：
- 座位資料會存入 seat_reservation 的 Kvrocks (不是 ScyllaDB)
- 票券資料會存入 ScyllaDB
"""

import asyncio
from uuid import UUID

from script.seating_config import SEATING_CONFIG_50000
from test.test_constants import SEED_EVENT_ID
from src.platform.database.scylla_setting import get_scylla_session
from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.driven_adapter.repo.event_ticketing_command_repo_scylla_impl import (
    EventTicketingCommandRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.user_command_repo_scylla_impl import (
    UserCommandRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.user_query_repo_scylla_impl import (
    UserQueryRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.event_ticketing_query_repo_scylla_impl import (
    EventTicketingQueryRepoScyllaImpl,
)
from src.platform.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)


async def create_init_users() -> UUID:
    """創建初始測試用戶 (1 seller + 25 buyers for distributed partition testing)

    Returns:
        int: seller_id
    """
    try:
        print('👥 Creating 26 users (1 seller + 25 buyers)...')

        user_repo = UserCommandRepoScyllaImpl()
        password_hasher = BcryptPasswordHasher()

        # 1. 創建 seller
        seller = UserEntity(
            email='s@t.com',
            name='init seller',
            role=UserRole.SELLER,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        seller.set_password('P@ssw0rd', password_hasher)
        created_seller = await user_repo.create(seller)
        print(f'   ✅ Created seller: ID={created_seller.id}, Email={created_seller.email}')

        # 2. 創建 25 個 buyers (用於測試 partition 分散)
        print('   🔄 Creating 25 buyers for distributed partition testing...')
        for i in range(1, 26):
            buyer = UserEntity(
                email=f'buyer_{i}@test.com',
                name=f'Buyer {i}',
                role=UserRole.BUYER,
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            buyer.set_password('P@ssw0rd', password_hasher)
            await user_repo.create(buyer)

            # Progress indicator every 5 users
            if i % 5 == 0:
                print(f'      Created {i}/25 buyers...')

        print('   ✅ Created 25 buyers')

        # Verify user count
        session = await get_scylla_session()
        result = await asyncio.to_thread(
            session.execute,
            'SELECT COUNT(*) FROM ticketing_system."user"'
        )
        row = result.one()
        user_count = row[0] if row else 0

        print(f'   📊 Total users: {user_count}')
        print(f'   📧 Seller: s@t.com / P@ssw0rd (ID={created_seller.id})')
        print(f'   📧 Buyers: buyer_1@test.com ~ buyer_25@test.com / P@ssw0rd')
        print(f'   💡 Load test will distribute requests across 25 different buyer_ids')

        if created_seller.id is None:
            raise Exception("Failed to create seller: ID is None")

        return created_seller.id

    except Exception as e:
        print(f'   ❌ Failed to create users: {e}')
        raise


async def create_init_event(seller_id: UUID):
    """創建初始測試活動"""
    try:
        print('🎫 Creating initial event...')

        # 確認用戶存在
        user_query_repo = UserQueryRepoScyllaImpl()
        user = await user_query_repo.get_by_id(seller_id)
        if user:
            print(f'   🔍 User found in DB: ID={user.id}, Email={user.email}')
        else:
            print(f'   ❌ User {seller_id} NOT found in database!')
            return None

        # 從 DI 容器取得所有依賴
        from src.platform.config.di import container

        event_ticketing_repo = EventTicketingCommandRepoScyllaImpl()
        init_state_handler = container.init_event_and_tickets_state_handler()
        mq_infra_orchestrator = container.mq_infra_orchestrator()

        # 創建 UseCase
        create_event_use_case = CreateEventAndTicketsUseCase(
            event_ticketing_command_repo=event_ticketing_repo,
            mq_infra_orchestrator=mq_infra_orchestrator,
            init_state_handler=init_state_handler,
        )

        # 座位配置選擇
        seating_config = SEATING_CONFIG_50000  

        # Calculate total seats
        total_seats = 0
        for section in seating_config['sections']:
            subsections = section.get('subsections', [])
            if not isinstance(subsections, (list, tuple)):
                print(f'   ⚠️  Warning: subsections is not iterable: {type(subsections)}')
                continue
            for subsection in subsections:
                if isinstance(subsection, dict):
                    total_seats += subsection['rows'] * subsection['seats_per_row']

        # 使用 UseCase 創建活動和票券 (使用固定的 event_id)
        event_aggregate = await create_event_use_case.create_event_and_tickets(
            name='Concert Event',
            description='Amazing live music performance',
            seller_id=seller_id,
            venue_name='Taipei Arena',
            seating_config=seating_config,
            is_active=True,
            event_id=SEED_EVENT_ID,  # 使用固定的 event_id 方便辨識和測試
        )

        event = event_aggregate.event
        tickets = event_aggregate.tickets

        print(f'   ✅ Created event: ID={event.id}, Name={event.name}')
        print(f'   ✅ Created tickets: {len(tickets)}')
        print('   🚀 Event created successfully!')

        return event.id

    except Exception as e:
        print(f'   ❌ Failed to create event: {e}')
        raise


async def verify_data():
    """驗證填充的資料"""
    try:
        print('🔍 Verifying seeded data...')
        session = await get_scylla_session()

        # Count users
        result = await asyncio.to_thread(
            session.execute,
            'SELECT COUNT(*) FROM ticketing_system."user"'
        )
        row = result.one()
        user_count = row[0] if row else 0
        print(f'   User count: {user_count}')

        # Count events
        result = await asyncio.to_thread(
            session.execute,
            'SELECT COUNT(*) FROM ticketing_system."event"'
        )
        row = result.one()
        event_count = row[0] if row else 0
        print(f'   Event count: {event_count}')

        # Count tickets
        result = await asyncio.to_thread(
            session.execute,
            'SELECT COUNT(*) FROM ticketing_system."ticket"'
        )
        row = result.one()
        ticket_count = row[0] if row else 0
        print(f'   Ticket count: {ticket_count}')

        # List users
        result = await asyncio.to_thread(
            session.execute,
            'SELECT id, email, role FROM ticketing_system."user"'
        )
        for row in result:
            print(f'      User ID={row.id}, Email={row.email}, Role={row.role}')

        # List events
        result = await asyncio.to_thread(
            session.execute,
            'SELECT id, name, seller_id FROM ticketing_system."event"'
        )
        for row in result:
            print(f'      Event ID={row.id}, Name={row.name}, Seller={row.seller_id}')

        print('   ✅ Data verification completed!')

    except Exception as e:
        print(f'   ❌ Failed to verify data: {e}')


async def main():
    print('🌱 Starting data seeding...')
    print('=' * 50)

    # Initialize Kvrocks connection pool before seeding
    from src.platform.state.kvrocks_client import kvrocks_client

    try:
        await kvrocks_client.initialize()
        print('📡 Kvrocks connection pool initialized')
    except Exception as e:
        print(f'❌ Failed to initialize Kvrocks: {e}')
        exit(1)

    try:
        # Create users and event (ScyllaDB commits happen per operation)
        seller_id = await create_init_users()
        print()

        await create_init_event(seller_id)
        print()

        await verify_data()
        print()

        print('=' * 50)
        print('🌱 Data seeding completed!')
        print('📋 Test accounts:')
        print('   Seller: s@t.com / P@ssw0rd')
        print('   Buyers: buyer_1@test.com ~ buyer_25@test.com / P@ssw0rd')
        print('   💡 Load test will distribute across 25 different buyer partitions')
        print()
        print(f'🎫 Fixed Event ID: {SEED_EVENT_ID}')
        print('   💡 All services will use this event_id for testing')

    except Exception as e:
        print(f'❌ Seeding failed: {e}')
        exit(1)
    finally:
        # Cleanup Kvrocks connection
        try:
            await kvrocks_client.disconnect_all()
            print('📡 Kvrocks connections closed')
        except Exception:
            pass


if __name__ == '__main__':
    asyncio.run(main())
