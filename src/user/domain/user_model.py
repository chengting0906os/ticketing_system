"""User models."""

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base
from src.user.domain.user_entity import UserRole


class User(SQLAlchemyBaseUserTable[int], Base):
    """User model."""

    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(  # type: ignore
        Integer,
        primary_key=True,
        autoincrement=True,
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
