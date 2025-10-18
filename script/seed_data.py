#!/usr/bin/env python3
"""
Database Seed Script
填充測試資料到資料庫

功能：
1. Create Users - 創建 12 個測試用戶 (1 seller + 1 buyer + 10 load test)
2. Create Event - 創建活動並發送座位初始化到 Kafka (→ seat_reservation Kvrocks)

注意：
- 座位資料會存入 seat_reservation 的 Kvrocks (不是 PostgreSQL)
- 票券資料會存入 event_ticketing 的 PostgreSQL
"""

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import text

from script.seating_config import  SEATING_CONFIG_50000
from src.platform.database.db_setting import async_session_maker
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


async def create_init_users_in_session(session) -> int:
    """創建初始測試用戶 (12 users total)

    Returns:
        int: seller_id
    """
    try:
        print('👥 Creating 12 users (1 seller + 1 buyer + 10 load test)...')

        @asynccontextmanager
        async def get_current_user_session():
            yield session

        user_repo = UserCommandRepoImpl(lambda: get_current_user_session())
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

        # 2. 創建 buyer
        buyer = UserEntity(
            email='b@t.com',
            name='init buyer',
            role=UserRole.BUYER,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        buyer.set_password('P@ssw0rd', password_hasher)
        created_buyer = await user_repo.create(buyer)
        print(f'   ✅ Created buyer: ID={created_buyer.id}, Email={created_buyer.email}')

        # 3. 批量創建 10 個 load test 用戶
        print('   📝 Creating 10 load test users...')
        for i in range(1, 11):
            loadtest_user = UserEntity(
                email=f'b_{i}@t.com',
                name=f'Load Test User {i}',
                role=UserRole.BUYER,
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            loadtest_user.set_password('P@ssw0rd', password_hasher)
            await user_repo.create(loadtest_user)

        print('   ✅ Created 10 load test users')

        result = await session.execute(text('SELECT COUNT(*) FROM "user"'))
        user_count = result.scalar()

        print(f'   📊 Total users: {user_count}')
        print(f'   📧 Seller: s@t.com / P@ssw0rd (ID={created_seller.id})')
        print(f'   📧 Buyer: b@t.com / P@ssw0rd')
        print(f'   📧 Load test: b_1@t.com ~ b_10@t.com / P@ssw0rd')

        if created_seller.id is None:
            raise Exception("Failed to create seller: ID is None")

        return created_seller.id

    except Exception as e:
        print(f'   ❌ Failed to create users: {e}')
        raise


async def create_init_event_in_session(session, seller_id: int):
    """創建初始測試活動"""
    try:
        print('🎫 Creating initial event...')

        # 確認用戶存在
        result = await session.execute(text(f'SELECT id, email FROM "user" WHERE id = {seller_id}'))
        user_check = result.fetchone()
        if user_check:
            print(f'   🔍 User found in DB: ID={user_check[0]}, Email={user_check[1]}')
        else:
            print(f'   ❌ User {seller_id} NOT found in database!')
            return None

        @asynccontextmanager
        async def get_current_session():
            yield session

        # 從 DI 容器取得所有依賴
        from src.platform.config.di import container

        # Command repo 使用 raw SQL，不需要 session
        event_ticketing_repo = EventTicketingCommandRepoImpl()
        init_state_handler = container.init_event_and_tickets_state_handler()
        mq_infra_orchestrator = container.mq_infra_orchestrator()

        # 創建 UseCase
        create_event_use_case = CreateEventAndTicketsUseCase(
            event_ticketing_command_repo=event_ticketing_repo,
            mq_infra_orchestrator=mq_infra_orchestrator,
            init_state_handler=init_state_handler,
        )

        # 座位配置選擇
        seating_config =  SEATING_CONFIG_50000  # 開發模式預設使用小規模配置

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

        # 使用 UseCase 創建活動和票券
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
        print('   🚀 Event created successfully!')

        return event.id

    except Exception as e:
        print(f'   ❌ Failed to create event: {e}')
        raise


async def verify_data():
    """驗證填充的資料"""
    # async_session_maker is a function that returns a sessionmaker
    async with async_session_maker()() as session:
        try:
            print('🔍 Verifying seeded data...')

            result = await session.execute(text('SELECT COUNT(*) FROM "user"'))
            user_count = result.scalar()
            print(f'   User count: {user_count}')

            result = await session.execute(text('SELECT COUNT(*) FROM event'))
            event_count = result.scalar()
            print(f'   Event count: {event_count}')

            result = await session.execute(text('SELECT COUNT(*) FROM ticket'))
            ticket_count = result.scalar()
            print(f'   Ticket count: {ticket_count}')

            result = await session.execute(text('SELECT id, email, role FROM "user" ORDER BY id'))
            users = result.fetchall()
            for user in users:
                print(f'      User ID={user[0]}, Email={user[1]}, Role={user[2]}')

            result = await session.execute(text('SELECT id, name, seller_id FROM event'))
            events = result.fetchall()
            for event in events:
                print(f'      Event ID={event[0]}, Name={event[1]}, Seller={event[2]}')

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
        # 使用單一 session 來處理所有數據操作
        # async_session_maker is a function that returns a sessionmaker
        async with async_session_maker()() as session:
            try:
                seller_id = await create_init_users_in_session(session)
                print()

                await create_init_event_in_session(session, seller_id)
                print()

                # 一次性提交所有操作
                await session.commit()
                print('✅ All data operations committed successfully!')

            except Exception as e:
                await session.rollback()
                print(f'❌ Rolling back all operations: {e}')
                raise

        await verify_data()
        print()

        print('=' * 50)
        print('🌱 Data seeding completed!')
        print('📋 Test accounts:')
        print('   Seller: s@t.com / P@ssw0rd')
        print('   Buyer:  b@t.com / P@ssw0rd')
        print('   Load test: b_1@t.com ~ b_10@t.com / P@ssw0rd')

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
