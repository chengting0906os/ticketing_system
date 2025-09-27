"""
User API Schemas - Pydantic models for request/response
"""

from pydantic import BaseModel, EmailStr, Field

from src.shared_kernel.user.domain.user_entity import UserRole


class CreateUserRequest(BaseModel):
    """Create user request schema"""

    email: EmailStr
    password: str = Field(
        ..., min_length=8, max_length=128, description='Password must be at least 8 characters'
    )
    name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    role: UserRole = UserRole.BUYER


class LoginRequest(BaseModel):
    """User login request schema"""

    email: EmailStr
    password: str = Field(..., min_length=1, description='User password')


class UserResponse(BaseModel):
    """User response schema"""

    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response schema"""

    user: UserResponse
    token: str


class ErrorResponse(BaseModel):
    """Error response schema"""

    detail: str
    error_code: str | None = None
