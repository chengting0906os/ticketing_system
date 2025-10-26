#!/usr/bin/env python3
"""
ScyllaDB Reset Script
重置 ScyllaDB 資料庫結構

功能：
1. Drop & Recreate Keyspace - 完全清空 ScyllaDB keyspace
2. Run Schema Initialization - 執行 scylla_schemas.cql
3. Flush Kvrocks - 清空 Kvrocks 所有資料

注意：
- 此腳本只重置資料庫結構，不填充測試資料
- 如需填充測試資料，請執行 `make seed` 或 `python script/seed_data.py`
"""

import asyncio
from pathlib import Path

from cassandra.cluster import Cluster

from src.platform.config.core_setting import settings
from src.platform.constant.path import BASE_DIR


def reset_scylladb_keyspace():
    """完全刪除並重新創建 ScyllaDB keyspace"""

    print(f'📊 Connecting to ScyllaDB: {settings.SCYLLA_CONTACT_POINTS}')

    try:
        # Connect to ScyllaDB cluster
        cluster = Cluster(
            contact_points=settings.SCYLLA_CONTACT_POINTS,
            port=settings.SCYLLA_PORT,
        )
        session = cluster.connect()

        print(f'🗑️  Dropping keyspace {settings.SCYLLA_KEYSPACE}...')

        # Drop keyspace if exists
        session.execute(f"DROP KEYSPACE IF EXISTS {settings.SCYLLA_KEYSPACE}")
        print(f'   ✅ Keyspace "{settings.SCYLLA_KEYSPACE}" dropped')

        # Read and execute schema file
        schema_file = Path(BASE_DIR) / 'src' / 'platform' / 'database' / 'scylla_schemas.cql'
        print(f'🏗️  Loading schema from {schema_file}...')

        if not schema_file.exists():
            raise FileNotFoundError(f'Schema file not found: {schema_file}')

        with open(schema_file, 'r') as f:
            schema_sql = f.read()

        # Split by semicolons
        raw_statements = schema_sql.split(';')

        # Clean and filter statements:
        # - Remove leading/trailing whitespace
        # - Remove comment-only lines (but keep SQL with inline comments)
        # - Keep statements that contain actual SQL keywords
        statements = []
        for stmt in raw_statements:
            # Remove comment lines but preserve the SQL content
            lines = [line for line in stmt.split('\n') if not line.strip().startswith('--')]
            cleaned = '\n'.join(lines).strip()
            if cleaned:  # If there's content after removing comments
                statements.append(cleaned)

        print(f'   📋 Found {len(statements)} SQL statements to execute')

        # Track if keyspace was created so we can reconnect
        keyspace_created = False

        for i, statement in enumerate(statements, 1):
            # Skip empty statements
            if not statement:
                continue

            # Execute CREATE KEYSPACE and then reconnect
            if statement.upper().startswith('CREATE KEYSPACE'):
                try:
                    session.execute(statement)
                    print(f'   ✅ Keyspace created')
                    keyspace_created = True
                    # Wait for keyspace to be fully created
                    import time

                    time.sleep(3)  # Give ScyllaDB time to sync schema
                    # Reconnect to the keyspace for subsequent table creation
                    session.shutdown()
                    session = cluster.connect(settings.SCYLLA_KEYSPACE)
                    print(f'   🔌 Connected to keyspace "{settings.SCYLLA_KEYSPACE}"')
                except Exception as e:
                    print(f'   ❌ Failed to create keyspace: {str(e)}')
                    raise
                continue

            # Skip USE statement - we're already connected to keyspace
            if statement.upper().startswith('USE '):
                continue

            try:
                session.execute(statement)
                print(f'   ✅ Statement {i}/{len(statements)} executed')
            except Exception as e:
                print(f'   ⚠️  Statement {i} failed: {str(e)[:100]}')
                # Don't raise - some statements like CREATE INDEX may fail if they already exist

        session.shutdown()
        cluster.shutdown()

        print('✅ ScyllaDB keyspace reset completed!')

    except Exception as e:
        print(f'❌ Failed to reset ScyllaDB: {e}')
        raise


async def flush_kvrocks():
    """清空 Kvrocks 所有資料"""
    try:
        import redis.asyncio as aioredis

        print('🗑️  Flushing Kvrocks...')
        client = await aioredis.from_url(
            f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=True,
        )

        # 清空所有資料
        await client.flushdb()
        await client.close()

        print('✅ Kvrocks flushed successfully!')

    except Exception as e:
        print(f'⚠️  Failed to flush Kvrocks (non-critical): {e}')
        print('    Kvrocks may not be running, continuing anyway...')


async def main():
    print('🔄 Starting ScyllaDB reset...')
    print('=' * 50)

    try:
        reset_scylladb_keyspace()
        print()

        await flush_kvrocks()
        print()

        print('=' * 50)
        print('✅ ScyllaDB reset completed!')
        print('💡 To seed test data, run: make seed')

    except Exception as e:
        print(f'❌ Reset failed: {e}')
        exit(1)


if __name__ == '__main__':
    asyncio.run(main())
