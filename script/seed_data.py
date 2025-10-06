#!/usr/bin/env python3
"""
Database Seed Script
填充測試資料到資料庫

功能：
1. Create Initial Users - 創建測試用 seller 和 buyer
2. Create Initial Event - 創建活動並發送座位初始化到 Kafka (→ seat_reservation Kvrocks)

注意：
- 此腳本會觸發座位初始化消息，需要 seat_reservation_mq_consumer 運行中
- 座位資料會存入 seat_reservation 的 Kvrocks (不是 PostgreSQL)
- 票券資料會存入 event_ticketing 的 PostgreSQL
"""

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import text

from script.seating_config import SEATING_CONFIG_3000
from src.platform.database.db_setting import async_session_maker
from src.platform.message_queue.kafka_config_service import KafkaConfigService
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


async def create_init_users_in_session(session):
    """創建初始測試用戶"""
    try:
        print('👥 Creating initial users...')

        @asynccontextmanager
        async def get_current_user_session():
            yield session

        user_repo = UserCommandRepoImpl(lambda: get_current_user_session())
        password_hasher = BcryptPasswordHasher()

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

        print('   ✅ Initial users created!')
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

        event_ticketing_repo = EventTicketingCommandRepoImpl(lambda: get_current_session())
        kafka_config = KafkaConfigService()

        # 從 DI 容器取得 init_state_handler
        from src.platform.config.di import container

        init_state_handler = container.init_event_and_tickets_state_handler()

        # 創建 UseCase
        create_event_use_case = CreateEventAndTicketsUseCase(
            session=session,
            event_ticketing_command_repo=event_ticketing_repo,
            kafka_service=kafka_config,
            init_state_handler=init_state_handler,
        )

        # 座位配置選擇
        seating_config = SEATING_CONFIG_3000  # 開發模式預設使用小規模配置

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
    async with async_session_maker() as session:
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

    try:
        # 使用單一 session 來處理所有數據操作
        async with async_session_maker() as session:
            try:
                seller_id = await create_init_users_in_session(session)
                print()

                await create_init_event_in_session(session, seller_id)  # type: ignore
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

    except Exception as e:
        print(f'❌ Seeding failed: {e}')
        exit(1)


if __name__ == '__main__':
    asyncio.run(main())
