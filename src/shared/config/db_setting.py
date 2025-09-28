from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.shared.config.core_setting import settings


engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    echo=False,
    future=True,
    # Connection pool settings for high-performance bulk operations
    pool_size=50,  # 常駐連線數
    max_overflow=50,  # 額外連線數
    pool_timeout=30,  # 取得連線超時
    pool_recycle=3600,  # 連線回收時間 (1小時)
    pool_pre_ping=True,  # 連線前測試
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
