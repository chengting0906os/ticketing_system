#!/usr/bin/env python3
"""
Database Reset Script
完整重置 PostgreSQL 資料庫

功能：
1. Drop & Recreate Database - 完全清空資料庫
2. Run Alembic Migrations - 建立最新的 schema
3. Create Initial Users - 創建測試用 seller 和 buyer
4. Create Initial Event - 創建活動並發送座位初始化到 Kafka (→ seat_reservation Kvrocks)

注意：
- 此腳本會觸發座位初始化消息，需要 seat_reservation_mq_consumer 運行中
- 座位資料會存入 seat_reservation 的 Kvrocks (不是 PostgreSQL)
- 票券資料會存入 event_ticketing 的 PostgreSQL
"""
import subprocess
import os
from src.shared.constant.path import BASE_DIR
import asyncio
import time
from sqlalchemy import create_engine, text

from src.shared.config.db_setting import Base

from src.booking.infra.booking_model import BookingModel, BookingTicketModel  # noqa: F401
from src.event_ticketing.infra.event_model import EventModel  # noqa: F401
from src.event_ticketing.infra.ticket_model import TicketModel  # noqa: F401
from src.shared_kernel.user.infra.user_model import UserModel  # noqa: F401

from src.event_ticketing.use_case.command.create_event_use_case import CreateEventUseCase
from src.event_ticketing.infra.event_ticketing_command_repo_impl import EventTicketingCommandRepoImpl
from src.shared.config.db_setting import async_session_maker
from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.infra.bcrypt_password_hasher import BcryptPasswordHasher
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl
from src.shared.config.core_setting import settings
from src.shared_infra.message_queue.kafka_config_service import KafkaConfigService
from scripts.seating_config import SEATING_CONFIG_50000, SEATING_CONFIG_30
from contextlib import asynccontextmanager


def get_database_url() -> str:
    """取得資料庫連接 URL"""

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

            # 等待一下確保完全清理
            
            time.sleep(1)

            # 重新創建資料庫
            conn.execute(text(f"CREATE DATABASE {db_name};"))
            print(f"   ✅ Database '{db_name}' created")

            # 等待確保資料庫完全創建
            time.sleep(1)

        admin_engine.dispose()

        print("🏗️ Running database migrations...")

        # 確保沒有應用程式運行來避免自動表創建
        print("   ⏸️ Ensuring no FastAPI app is running during migration...")

        # 運行 Alembic 遷移
        

        # 設置環境變量防止 SQLAlchemy 自動創建表
        env = os.environ.copy()
        env['SKIP_DB_INIT'] = 'true'

        # 首先檢查資料庫是否真的是空的
        print("   🔍 Verifying database is empty...")
        table_count = 0
        check_engine = create_engine(sync_url)
        try:
            with check_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                """))
                table_count = result.scalar() or 0
                print(f"   📊 Found {table_count} existing tables")

                if table_count > 0:
                    print("   🧹 Database not empty, recreating it again...")
        finally:
            check_engine.dispose()

        # 如果需要重新創建，在外面執行以避免連接問題
        if table_count > 0:
            # 重新創建資料庫確保完全乾淨
            admin_engine = create_engine(f"{server_url}/postgres", isolation_level="AUTOCOMMIT")
            try:
                with admin_engine.connect() as admin_conn:
                    admin_conn.execute(text(f"""
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = '{db_name}' AND pid <> pg_backend_pid();
                    """))
                    admin_conn.execute(text(f"DROP DATABASE IF EXISTS {db_name};"))
                    time.sleep(1)
                    admin_conn.execute(text(f"CREATE DATABASE {db_name};"))
                    time.sleep(1)
            finally:
                admin_engine.dispose()

            print("   ✅ Database recreated and verified empty")

        # 運行 alembic upgrade head (alembic.ini 在專案根目錄)
        print("   🔄 Running 'alembic upgrade head'...")
        result = subprocess.run(
            ['alembic', 'upgrade', 'head'],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            env=env
        )

        if result.returncode == 0:
            print("   ✅ Database migrations completed")
            if result.stdout:
                print(f"   📋 Output: {result.stdout.strip()}")
        else:
            print(f"   ❌ Migration failed (return code: {result.returncode})")
            if result.stdout:
                print(f"   📋 STDOUT: {result.stdout}")
            if result.stderr:
                print(f"   📋 STDERR: {result.stderr}")
            raise Exception(f"Alembic migration failed with return code {result.returncode}")

        print("Database recreation completed!")

    except Exception as e:
        print(f"❌ Failed to recreate database: {e}")
        raise


async def create_init_users_in_session(session):
        try:
            print("Creating initial users...")

            # 創建一個使用當前 session 的 repo


            @asynccontextmanager
            async def get_current_user_session():
                yield session

            user_repo = UserCommandRepoImpl(lambda: get_current_user_session())
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

            # Note: commit will be handled by main() function
            print("Initial users created!")
            return created_seller.id

        except Exception as e:
            print(f"Failed to create users: {e}")
            raise


async def create_init_event_in_session(session, seller_id: int):
        try:
            # 調試：確認用戶是否存在於數據庫中
            from sqlalchemy import text
            result = await session.execute(text(f'SELECT id, email FROM "user" WHERE id = {seller_id}'))
            user_check = result.fetchone()
            if user_check:
                print(f"   🔍 User found in DB: ID={user_check[0]}, Email={user_check[1]}")
            else:
                print(f"   ❌ User {seller_id} NOT found in database!")
                return None

            @asynccontextmanager
            async def get_current_session():
                yield session

            event_ticketing_repo = EventTicketingCommandRepoImpl(lambda: get_current_session())
            kafka_config = KafkaConfigService()

            # 創建 UseCase
            create_event_use_case = CreateEventUseCase(
                session=session,
                event_ticketing_command_repo=event_ticketing_repo,
                kafka_service=kafka_config
            )

            # 座位配置選擇
            # SEATING_CONFIG_30: 開發測試用（30 個座位，快速初始化）
            # SEATING_CONFIG_50000: 生產環境用（50,000 個座位，完整壓力測試）
            seating_config = SEATING_CONFIG_50000  # 開發模式預設使用小規模配置

            # Calculate total seats from nested structure: sections → subsections → rows × seats_per_row
            total_seats = sum(
                subsection['rows'] * subsection['seats_per_row']
                for section in seating_config['sections']
                for subsection in section['subsections']
            )

            # 使用 UseCase 的 create_event_and_tickets 方法
            # 這會發送座位初始化消息到 Kafka → seat_reservation_mq_consumer → Kvrocks
            event_aggregate = await create_event_use_case.create_event_and_tickets(
                name="Concert Event",
                description="Amazing live music performance",
                seller_id=seller_id,
                venue_name="Taipei Arena",
                seating_config=seating_config,
                is_active=True,
            )

            event = event_aggregate.event
            tickets = event_aggregate.tickets

            print(f"   ✅ Created event: ID={event.id}, Name={event.name}")
            print(f"   ✅ Created tickets: {len(tickets)}")
            print(f"   🚀 Event created successfully via UseCase")

            print("✨ Initial event and tickets created using CreateEventUseCase!")
            return event.id

        except Exception as e:
            print(f"❌ Failed to create event: {e}")
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


async def flush_kvrocks():
    """清空 Kvrocks 所有資料"""
    try:
        import redis.asyncio as aioredis

        print("🗑️  Flushing Kvrocks...")
        client = await aioredis.from_url(
            f"redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}",
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=True,
        )

        # 清空所有資料
        await client.flushdb()
        await client.close()

        print("✅ Kvrocks flushed successfully!")

    except Exception as e:
        print(f"⚠️  Failed to flush Kvrocks (non-critical): {e}")
        print("    Kvrocks may not be running, continuing anyway...")


async def main():
    print("Starting database reset...")
    print("=" * 50)

    try:
        await drop_and_recreate_database()
        print()

        await flush_kvrocks()
        print()

        # 使用單一 session 來處理所有數據操作
        async with async_session_maker() as session:
            try:
                seller_id = await create_init_users_in_session(session)
                print()

                await create_init_event_in_session(session, seller_id) # type: ignore
                print()

                # 一次性提交所有操作
                await session.commit()
                print("✅ All data operations committed successfully!")

            except Exception as e:
                await session.rollback()
                print(f"❌ Rolling back all operations: {e}")
                raise

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
