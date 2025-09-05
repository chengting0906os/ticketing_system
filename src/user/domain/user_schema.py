"""User schemas."""

import uuid

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr, Field

from src.user.domain.user_model import UserRole


class UserRead(schemas.BaseUser[uuid.UUID]):
    """User read schema."""
    
    id: uuid.UUID
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False

class UserPublic(BaseModel):
    """Simplified user schema for public API."""
    
    id: uuid.UUID
    name: str
    email: EmailStr
    role: UserRole


class UserCreate(schemas.BaseUserCreate):
    """User creation schema."""
    
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.BUYER


class UserUpdate(schemas.BaseUserUpdate):
    """User update schema."""
    
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    role: UserRole | None = None
