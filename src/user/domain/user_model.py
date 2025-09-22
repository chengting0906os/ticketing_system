from datetime import datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.shared.config.db_setting import Base
from src.user.domain.user_entity import UserRole


class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(  # type: ignore
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(  # pyright: ignore[reportIncompatibleVariableOverride]
        String(255),
        nullable=False,
        unique=True,
    )
    hashed_password: Mapped[str] = mapped_column(  # pyright: ignore[reportIncompatibleVariableOverride]
        String(255), nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=UserRole.BUYER,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(  # pyright: ignore[reportIncompatibleVariableOverride]
        Boolean, default=True, nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(  # pyright: ignore[reportIncompatibleVariableOverride]
        Boolean, default=False, nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(  # pyright: ignore[reportIncompatibleVariableOverride]
        Boolean, default=False, nullable=False
    )
