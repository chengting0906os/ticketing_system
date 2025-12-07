#!/usr/bin/env python3
"""
Database Reset Script
重置 PostgreSQL 資料庫結構

功能：
1. Drop & Recreate Database - 完全清空資料庫
2. Run Alembic Migrations - 建立最新的 schema
3. Flush Kvrocks - 清空 Kvrocks 所有資料

注意：
- 此腳本只重置資料庫結構，不填充測試資料
- 如需填充測試資料，請執行 `make seed` 或 `python script/seed_data.py`
"""

import asyncio
import os
import subprocess
import time

from sqlalchemy import create_engine, text

from src.platform.config.core_setting import settings
from src.platform.constant.path import BASE_DIR


def get_database_url() -> str:
    """取得資料庫連接 URL"""

    return settings.DATABASE_URL_ASYNC


async def drop_and_recreate_database():
    """完全刪除並重新創建資料庫"""
    database_url = get_database_url()
    print(f'Database URL: {database_url}')

    # 解析資料庫連接信息
    if database_url.startswith('postgresql+asyncpg://'):
        sync_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')
    else:
        sync_url = database_url

    # 提取資料庫名稱
    db_name = sync_url.split('/')[-1]
    server_url = sync_url.rsplit('/', 1)[0]

    print(f'Server URL: {server_url}')
    print(f'Database name: {db_name}')

    try:
        print('🗑️ Dropping database...')

        # 連接到 postgres 預設資料庫以執行 DROP/CREATE
        admin_engine = create_engine(f'{server_url}/postgres', isolation_level='AUTOCOMMIT')

        with admin_engine.connect() as conn:
            # 關閉現有連接
            conn.execute(
                text(f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{db_name}' AND pid <> pg_backend_pid();
            """)
            )

            # 刪除資料庫
            conn.execute(text(f'DROP DATABASE IF EXISTS {db_name};'))
            print(f"   ✅ Database '{db_name}' dropped")

            # 等待一下確保完全清理

            time.sleep(1)

            # 重新創建資料庫
            conn.execute(text(f'CREATE DATABASE {db_name};'))
            print(f"   ✅ Database '{db_name}' created")

            # 等待確保資料庫完全創建
            time.sleep(1)

        admin_engine.dispose()

        print('🏗️ Running database migrations...')

        # 確保沒有應用程式運行來避免自動表創建
        print('   ⏸️ Ensuring no FastAPI app is running during migration...')

        # 運行 Alembic 遷移

        # 設置環境變量防止 SQLAlchemy 自動創建表
        env = os.environ.copy()
        env['SKIP_DB_INIT'] = 'true'

        # 首先檢查資料庫是否真的是空的
        print('   🔍 Verifying database is empty...')
        table_count = 0
        check_engine = create_engine(sync_url)
        try:
            with check_engine.connect() as conn:
                result = conn.execute(
                    text("""
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                )
                table_count = result.scalar() or 0
                print(f'   📊 Found {table_count} existing tables')

                if table_count > 0:
                    print('   🧹 Database not empty, recreating it again...')
        finally:
            check_engine.dispose()

        # 如果需要重新創建，在外面執行以避免連接問題
        if table_count > 0:
            # 重新創建資料庫確保完全乾淨
            admin_engine = create_engine(f'{server_url}/postgres', isolation_level='AUTOCOMMIT')
            try:
                with admin_engine.connect() as admin_conn:
                    admin_conn.execute(
                        text(f"""
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = '{db_name}' AND pid <> pg_backend_pid();
                    """)
                    )
                    admin_conn.execute(text(f'DROP DATABASE IF EXISTS {db_name};'))
                    time.sleep(1)
                    admin_conn.execute(text(f'CREATE DATABASE {db_name};'))
                    time.sleep(1)
            finally:
                admin_engine.dispose()

            print('   ✅ Database recreated and verified empty')

        # 運行 alembic upgrade head (alembic.ini 在專案根目錄)
        print("   🔄 Running 'alembic upgrade head'...")
        result = subprocess.run(
            ['alembic', 'upgrade', 'head'], cwd=BASE_DIR, capture_output=True, text=True, env=env
        )

        if result.returncode == 0:
            print('   ✅ Database migrations completed')
            if result.stdout:
                print(f'   📋 Output: {result.stdout.strip()}')
        else:
            print(f'   ❌ Migration failed (return code: {result.returncode})')
            if result.stdout:
                print(f'   📋 STDOUT: {result.stdout}')
            if result.stderr:
                print(f'   📋 STDERR: {result.stderr}')
            raise Exception(f'Alembic migration failed with return code {result.returncode}')

        print('Database recreation completed!')

    except Exception as e:
        print(f'❌ Failed to recreate database: {e}')
        raise


async def flush_kvrocks():
    """清空 Kvrocks 所有資料（支援 Cluster 模式）"""
    try:
        from src.platform.state.kvrocks_client import get_kvrocks_client

        print('🗑️  Flushing Kvrocks...')
        client = await get_kvrocks_client()

        # Cluster 模式需要對每個節點執行 FLUSHDB
        if settings.KVROCKS_CLUSTER_MODE:
            # 對所有 master 節點執行 flushdb
            await client.flushdb(target_nodes='primaries')
        else:
            await client.flushdb()

        await client.aclose()
        print('✅ Kvrocks flushed successfully!')

    except Exception as e:
        print(f'⚠️  Failed to flush Kvrocks (non-critical): {e}')
        print('    Kvrocks may not be running, continuing anyway...')


async def main():
    print('🔄 Starting database reset...')
    print('=' * 50)

    try:
        await drop_and_recreate_database()
        print()

        await flush_kvrocks()
        print()

        print('=' * 50)
        print('✅ Database reset completed!')
        print('💡 To seed test data, run: make seed')

    except Exception as e:
        print(f'❌ Reset failed: {e}')
        exit(1)


if __name__ == '__main__':
    asyncio.run(main())
