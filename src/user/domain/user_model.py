"""User models."""

from enum import Enum

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class UserRole(str, Enum):
    """User roles."""
    
    ORGANIZER = 'organizer'
    CUSTOMER = 'customer'


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model."""
    
    __tablename__ = 'users'
    
    first_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=UserRole.CUSTOMER,
        nullable=False,
    )
