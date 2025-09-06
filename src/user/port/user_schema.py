"""User schemas."""

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr, Field


# UserRole validation will be done in domain layer, not schema


class UserRead(schemas.BaseUser[int]):
    """User read schema."""

    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False


class UserPublic(BaseModel):
    """Simplified user schema for public API."""

    id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'name': 'John Doe',
                'email': 'john.doe@example.com',
                'role': 'buyer',
            }
        }


class UserCreate(schemas.BaseUserCreate):
    """User creation schema."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = 'buyer'

    class Config:
        json_schema_extra = {
            'example': {
                'name': 'Jane Smith',
                'email': 'jane.smith@example.com',
                'password': 'SecurePass123!',
                'role': 'seller',
            }
        }


class UserUpdate(schemas.BaseUserUpdate):
    """User update schema."""

    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    role: str | None = None

    class Config:
        json_schema_extra = {
            'example': {
                'name': 'Jane Doe Updated',
                'email': 'jane.new@example.com',
                'role': 'buyer',
            }
        }
