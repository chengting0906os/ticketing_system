#!/usr/bin/env python3
"""
Database Reset Script
Reset PostgreSQL database structure

Features:
1. Drop & Recreate Database - completely wipe the database
2. Run Alembic Migrations - create the latest schema
3. Flush Kvrocks - clear all Kvrocks data

Notes:
- This script only resets database structure, does not seed test data
- To seed test data, run `make seed` or `python script/seed_data.py`
"""

import asyncio
import os
import subprocess
import time

import redis.asyncio as aioredis
from sqlalchemy import create_engine, text

from src.platform.config.core_setting import settings
from src.platform.constant.path import BASE_DIR

DB_WAIT_SECONDS = 1


def _get_sync_url(async_url: str) -> str:
    """Convert async database URL to sync URL"""
    if async_url.startswith('postgresql+asyncpg://'):
        return async_url.replace('postgresql+asyncpg://', 'postgresql://')
    return async_url


def _parse_db_connection(database_url: str) -> tuple[str, str]:
    """Parse database URL and return (server_url, db_name)"""
    sync_url = _get_sync_url(database_url)
    db_name = sync_url.split('/')[-1]
    server_url = sync_url.rsplit('/', 1)[0]
    return server_url, db_name


def _terminate_connections(conn, db_name: str) -> None:
    """Terminate all connections to the specified database"""
    conn.execute(
        text(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{db_name}' AND pid <> pg_backend_pid();
        """)
    )


def _drop_and_create_db(server_url: str, db_name: str) -> None:
    """Drop and recreate database"""
    admin_engine = create_engine(f'{server_url}/postgres', isolation_level='AUTOCOMMIT')

    try:
        with admin_engine.connect() as conn:
            _terminate_connections(conn, db_name)

            conn.execute(text(f'DROP DATABASE IF EXISTS {db_name};'))
            print(f"   ✅ Database '{db_name}' dropped")

            time.sleep(DB_WAIT_SECONDS)

            conn.execute(text(f'CREATE DATABASE {db_name};'))
            print(f"   ✅ Database '{db_name}' created")

            time.sleep(DB_WAIT_SECONDS)
    finally:
        admin_engine.dispose()


def _count_tables(sync_url: str) -> int:
    """Count existing tables in the database"""
    check_engine = create_engine(sync_url)

    try:
        with check_engine.connect() as conn:
            result = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            )
            return result.scalar() or 0
    finally:
        check_engine.dispose()


def _run_alembic_migrations() -> None:
    """Run Alembic migrations"""
    print("   🔄 Running 'alembic upgrade head'...")

    env = os.environ.copy()
    env['SKIP_DB_INIT'] = 'true'

    result = subprocess.run(
        ['alembic', 'upgrade', 'head'],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        print(f'   ❌ Migration failed (return code: {result.returncode})')
        if result.stdout:
            print(f'   📋 STDOUT: {result.stdout}')
        if result.stderr:
            print(f'   📋 STDERR: {result.stderr}')
        raise Exception(f'Alembic migration failed with return code {result.returncode}')

    print('   ✅ Database migrations completed')
    if result.stdout:
        print(f'   📋 Output: {result.stdout.strip()}')


async def drop_and_recreate_database():
    """Completely drop and recreate database"""
    database_url = settings.DATABASE_URL_ASYNC
    server_url, db_name = _parse_db_connection(database_url)

    print(f'Database URL: {database_url}')
    print(f'Server URL: {server_url}')
    print(f'Database name: {db_name}')

    try:
        # Initial drop and create
        print('🗑️ Dropping database...')
        _drop_and_create_db(server_url, db_name)

        print('🏗️ Running database migrations...')
        print('   ⏸️ Ensuring no FastAPI app is running during migration...')

        # Verify database is empty
        print('   🔍 Verifying database is empty...')
        sync_url = _get_sync_url(database_url)
        table_count = _count_tables(sync_url)
        print(f'   📊 Found {table_count} existing tables')

        # Recreate if not empty
        if table_count > 0:
            print('   🧹 Database not empty, recreating it again...')
            _drop_and_create_db(server_url, db_name)
            print('   ✅ Database recreated and verified empty')

        _run_alembic_migrations()
        print('Database recreation completed!')

    except Exception as e:
        print(f'❌ Failed to recreate database: {e}')
        raise


async def flush_kvrocks():
    """Flush all Kvrocks data"""
    try:
        print('🗑️  Flushing Kvrocks...')

        client = await aioredis.from_url(
            f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=True,
        )

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
