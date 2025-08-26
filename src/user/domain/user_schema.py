"""User schemas."""

import uuid

from fastapi_users import schemas
from pydantic import EmailStr, Field

from src.user.domain.user_model import UserRole


class UserRead(schemas.BaseUser[uuid.UUID]):
    """User read schema."""
    
    id: uuid.UUID
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False


class UserCreate(schemas.BaseUserCreate):
    """User creation schema."""
    
    first_name: str = Field(..., min_length=1, max_length=150)
    last_name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.CUSTOMER


class UserUpdate(schemas.BaseUserUpdate):
    """User update schema."""
    
    first_name: str | None = Field(None, min_length=1, max_length=150)
    last_name: str | None = Field(None, min_length=1, max_length=150)
    email: EmailStr | None = None
    role: UserRole | None = None
