"""Script to create database tables."""

import asyncio

from src.order.infra.order_model import OrderModel  # Import order models
from src.product.infra.product_model import ProductModel  # Import product models
from src.shared.database import Base, engine
from src.user.domain.user_model import (
    User,  # 重要：必須 import 所有 model 讓 SQLAlchemy 知道它們存在
)


async def init_db():
    """Initialize database with tables."""
    async with engine.begin() as conn:
        # Drop all tables first (for development)
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())
