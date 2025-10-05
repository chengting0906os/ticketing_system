"""
User API Schemas - Pydantic models for request/response
"""

from pydantic import BaseModel, EmailStr, Field, SecretStr

from src.service.ticketing.domain.user_entity import UserRole


class CreateUserRequest(BaseModel):
    """Create user request schema"""

    email: EmailStr
    password: SecretStr = Field(
        ...,
        min_length=8,
        max_length=30,
        description='Password must be 8-30 characters (bcrypt limit)',
    )
    name: str = Field(..., min_length=1, max_length=100)
    role: UserRole = UserRole.BUYER

    class Config:
        json_schema_extra = {
            'example': {
                'email': 'user@example.com',
                'password': 'P@ssw0rd',
                'name': 'John Doe',
                'role': 'buyer',
            }
        }


class LoginRequest(BaseModel):
    """User login request schema"""

    email: EmailStr
    password: SecretStr = Field(
        ..., min_length=1, max_length=72, description='User password (max 72 chars)'
    )

    class Config:
        json_schema_extra = {'example': {'email': 'b@t.com', 'password': 'P@ssw0rd'}}


class UserResponse(BaseModel):
    """User response schema"""

    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True
        json_schema_extra = {
            'example': {
                'id': 1,
                'email': 'user@example.com',
                'name': 'John Doe',
                'role': 'buyer',
                'is_active': True,
            }
        }
