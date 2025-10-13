"""
Database configuration (legacy compatibility layer)

This module re-exports from:
- orm_db_setting.py: SQLAlchemy engine/session management
- asyncpg_setting.py: asyncpg connection pool for bulk operations

DEPRECATED: Import directly from orm_db_setting or asyncpg_setting instead
"""

# SQLAlchemy (ORM)
from src.platform.database.orm_db_setting import (
    Base,
    Database,
    async_session_maker,
    create_db_and_tables,
    engine,
    get_async_session,
    get_async_read_session,
)

# asyncpg (raw SQL for bulk operations)
from src.platform.database.asyncpg_setting import close_asyncpg_pool, get_asyncpg_pool

__all__ = [
    # SQLAlchemy
    'Base',
    'Database',
    'engine',
    'async_session_maker',
    'create_db_and_tables',
    'get_async_session',
    'get_async_read_session',
    # asyncpg
    'get_asyncpg_pool',
    'close_asyncpg_pool',
]
