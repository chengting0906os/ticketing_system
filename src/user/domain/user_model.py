"""User models."""

from enum import Enum

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class UserRole(str, Enum):
    """User roles."""
    
    SELLER = 'seller'
    BUYER = 'buyer'


class User(SQLAlchemyBaseUserTable[int], Base):
    """User model."""
    
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column( # type: ignore
        Integer,  
        primary_key=True, 
        autoincrement=True,
        server_default=text("nextval('users_id_seq'::regclass)")
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
