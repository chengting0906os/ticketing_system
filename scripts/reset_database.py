#!/usr/bin/env python3

import asyncio

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.shared.config.db_setting import Base

# Import all SQLAlchemy models so they are registered with Base.metadata
from src.booking.infra.booking_model import BookingModel, BookingTicketModel  # noqa: F401
from src.event_ticketing.infra.event_model import EventModel  # noqa: F401
from src.event_ticketing.infra.ticket_model import TicketModel  # noqa: F401
from src.shared_kernel.user.infra.user_model import UserModel  # noqa: F401

from src.event_ticketing.domain.event_entity import Event, EventStatus
from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus as TicketStatus
from src.event_ticketing.infra.event_command_repo_impl import EventCommandRepoImpl
from src.event_ticketing.infra.ticket_command_repo_impl import TicketCommandRepoImpl
from src.shared.config.db_setting import async_session_maker
from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.infra.bcrypt_password_hasher import BcryptPasswordHasher
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl


def get_database_url() -> str:
    """取得資料庫連接 URL"""
    from src.shared.config.core_setting import settings
    return settings.DATABASE_URL_ASYNC


async def drop_and_recreate_database():
    """完全刪除並重新創建資料庫"""
    database_url = get_database_url()
    print(f"Database URL: {database_url}")

    # 解析資料庫連接信息
    if database_url.startswith('postgresql+asyncpg://'):
        sync_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')
    else:
        sync_url = database_url

    # 提取資料庫名稱
    db_name = sync_url.split('/')[-1]
    server_url = sync_url.rsplit('/', 1)[0]

    print(f"Server URL: {server_url}")
    print(f"Database name: {db_name}")

    try:
        print("🗑️ Dropping database...")

        # 連接到 postgres 預設資料庫以執行 DROP/CREATE
        admin_engine = create_engine(f"{server_url}/postgres", isolation_level="AUTOCOMMIT")

        with admin_engine.connect() as conn:
            # 關閉現有連接
            conn.execute(text(f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{db_name}' AND pid <> pg_backend_pid();
            """))

            # 刪除資料庫
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name};"))
            print(f"   ✅ Database '{db_name}' dropped")

            # 重新創建資料庫
            conn.execute(text(f"CREATE DATABASE {db_name};"))
            print(f"   ✅ Database '{db_name}' created")

        admin_engine.dispose()

        print("🏗️ Creating database schema...")

        # 創建所有表格
        async_engine = create_async_engine(database_url)
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("   ✅ All tables created")

        await async_engine.dispose()

        print("Database recreation completed!")

    except Exception as e:
        print(f"❌ Failed to recreate database: {e}")
        raise


async def create_init_users():
    async with async_session_maker() as session:
        try:
            print("Creating initial users...")

            user_repo = UserCommandRepoImpl(session)
            password_hasher = BcryptPasswordHasher()

            seller = UserEntity(
                email="s@t.com",
                name="init seller",
                role=UserRole.SELLER,
                is_active=True,
                is_superuser=False,
                is_verified=True
            )
            seller.set_password("P@ssw0rd", password_hasher)
            created_seller = await user_repo.create(seller)
            print(f"   Created seller: ID={created_seller.id}, Email={created_seller.email}")

            buyer = UserEntity(
                email="b@t.com",
                name="init buyer",
                role=UserRole.BUYER,
                is_active=True,
                is_superuser=False,
                is_verified=True
            )
            buyer.set_password("P@ssw0rd", password_hasher)
            created_buyer = await user_repo.create(buyer)
            print(f"   Created buyer: ID={created_buyer.id}, Email={created_buyer.email}")

            print("Initial users created!")
            return created_seller.id

        except Exception as e:
            print(f"Failed to create users: {e}")
            raise


async def create_init_event(seller_id: int):
    async with async_session_maker() as session:
        try:
            print("Creating initial event...")

            event_repo = EventCommandRepoImpl(session)
            ticket_repo = TicketCommandRepoImpl(session)

            seating_config = {
                "sections": [
                    {
                        "name": "A",
                        "price": 3000,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "B",
                        "price": 2800,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "C",
                        "price": 2500,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "D",
                        "price": 2200,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "E",
                        "price": 2000,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "F",
                        "price": 1800,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "G",
                        "price": 1500,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "H",
                        "price": 1200,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "I",
                        "price": 1000,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    },
                    {
                        "name": "J",
                        "price": 800,
                        "subsections": [{"number": i, "rows": 25, "seats_per_row": 20} for i in range(1, 11)]
                    }
                ]
            }

            event = Event(
                name="Concert Event",
                description="Amazing live music performance",
                seller_id=seller_id,
                venue_name="Taipei Arena",
                seating_config=seating_config,
                is_active=True,
                status=EventStatus.AVAILABLE
            )

            created_event = await event_repo.create(event=event)
            print(f"   Created event: ID={created_event.id}, Name={created_event.name}")

            print("Generating tickets...")
            tickets = []
            total_tickets = 0

            for section in seating_config["sections"]:
                section_name = section["name"]
                section_price = section["price"]

                for subsection in section["subsections"]:
                    subsection_number = subsection["number"]
                    rows = subsection["rows"]
                    seats_per_row = subsection["seats_per_row"]

                    for row in range(1, rows + 1):
                        for seat in range(1, seats_per_row + 1):
                            ticket = Ticket(
                                event_id=created_event.id, # type: ignore
                                section=section_name,
                                subsection=subsection_number,
                                row=row,
                                seat=seat,
                                price=section_price,
                                status=TicketStatus.AVAILABLE
                            )
                            tickets.append(ticket)
                            total_tickets += 1

            await ticket_repo.create_batch(tickets=tickets)
            await session.commit()  # 明確提交票務數據
            print(f"   Created tickets: {total_tickets}")

            print("Initial event and tickets created!")
            return created_event.id

        except Exception as e:
            print(f"Failed to create event: {e}")
            await session.rollback()
            raise


async def verify_data():
    async with async_session_maker() as session:
        try:
            print("Verifying data...")

            result = await session.execute(text('SELECT COUNT(*) FROM "user"'))
            user_count = result.scalar()
            print(f"   User count: {user_count}")

            result = await session.execute(text('SELECT COUNT(*) FROM event'))
            event_count = result.scalar()
            print(f"   Event count: {event_count}")

            result = await session.execute(text('SELECT COUNT(*) FROM ticket'))
            ticket_count = result.scalar()
            print(f"   Ticket count: {ticket_count}")

            result = await session.execute(text('SELECT id, email, role FROM "user" ORDER BY id'))
            users = result.fetchall()
            for user in users:
                print(f"      User ID={user[0]}, Email={user[1]}, Role={user[2]}")

            result = await session.execute(text('SELECT id, name, seller_id FROM event'))
            events = result.fetchall()
            for event in events:
                print(f"      Event ID={event[0]}, Name={event[1]}, Seller={event[2]}")

            print("Data verification completed!")

        except Exception as e:
            print(f"Failed to verify data: {e}")


async def main():
    print("Starting database reset...")
    print("=" * 50)

    try:
        await drop_and_recreate_database()
        print()

        seller_id = await create_init_users()
        print()

        await create_init_event(seller_id) # type: ignore
        print()

        await verify_data()
        print()

        print("=" * 50)
        print("Database reset completed!")
        print("Test accounts:")
        print("   Seller: s@t.com / P@ssw0rd")
        print("   Buyer:  b@t.com / P@ssw0rd")

    except Exception as e:
        print(f"Reset failed: {e}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
