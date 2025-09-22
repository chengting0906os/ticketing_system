from typing import Any, Dict, Optional

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
import jwt

from src.shared.config.core_setting import settings
from src.user.domain.user_model import User
from src.user.use_case.manager import get_user_manager


class CustomJWTStrategy(JWTStrategy):
    """Custom JWT Strategy that includes user data in the payload"""

    async def write_token(self, user: User) -> str:
        """Create JWT token with custom user data in payload"""
        from datetime import datetime, timedelta, timezone

        # Create the payload with user data
        data = {
            'sub': str(user.id),  # Subject (user ID) - standard claim
            'aud': 'fastapi-users:auth',  # Audience - standard claim
            # Custom user data
            'user_id': user.id,
            'email': user.email,
            'name': user.name,
            'role': user.role,
            'is_active': user.is_active,
            'is_verified': user.is_verified,
            'is_superuser': user.is_superuser,
        }

        # Add expiration time if lifetime is set
        if self.lifetime_seconds:
            data['exp'] = int(
                (datetime.now(timezone.utc) + timedelta(seconds=self.lifetime_seconds)).timestamp()
            )

        # Encode the token - convert secret to string if needed
        secret_value = self.secret if isinstance(self.secret, (str, bytes)) else str(self.secret)
        token = jwt.encode(data, secret_value, algorithm=self.algorithm)
        return token

    async def read_token(self, token: Optional[str], user_manager: Any) -> Optional[User]:
        """Decode JWT token and return user"""
        if token is None:
            return None

        try:
            # Decode the token - convert secret to string if needed
            secret_value = (
                self.secret if isinstance(self.secret, (str, bytes)) else str(self.secret)
            )
            data = jwt.decode(
                token, secret_value, audience='fastapi-users:auth', algorithms=[self.algorithm]
            )

            # Get user ID from the payload
            user_id = data.get('sub')
            if user_id is None:
                return None

            # Fetch user from database using user manager
            try:
                user_id = int(user_id)
                user = await user_manager.get(user_id)
                return user
            except (ValueError, Exception):
                return None

        except jwt.PyJWTError:
            return None

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode token and return the full payload (for debugging/inspection)"""
        try:
            # Convert secret to string if needed
            secret_value = (
                self.secret if isinstance(self.secret, (str, bytes)) else str(self.secret)
            )
            payload = jwt.decode(
                token, secret_value, audience='fastapi-users:auth', algorithms=[self.algorithm]
            )
            return payload
        except jwt.PyJWTError:
            return None

    def decode_token_simple(self, token: str) -> Optional[Dict[str, Any]]:
        """Simple token decode without verification (for testing/debugging)"""
        try:
            # Convert secret to string if needed
            secret_value = (
                self.secret if isinstance(self.secret, (str, bytes)) else str(self.secret)
            )
            # Decode without verification for simple inspection
            payload = jwt.decode(
                token,
                secret_value,
                algorithms=[self.algorithm],
                options={'verify_signature': True, 'verify_exp': True, 'verify_aud': False},
            )
            return payload
        except jwt.PyJWTError:
            return None

    def decode_full_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode token and return the full payload (alias for decode_token)"""
        return self.decode_token(token)


class JWTAuthService:
    def __init__(self):
        self.cookie_transport = CookieTransport(
            cookie_name='fastapiusersauth',
            cookie_max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            cookie_secure=False,  # Set to True in production with HTTPS
            cookie_httponly=True,
            cookie_samesite='lax',
        )

        # Use custom JWT strategy with user data in payload
        self.jwt_strategy = CustomJWTStrategy(
            secret=settings.SECRET_KEY.get_secret_value(),
            lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            algorithm=settings.ALGORITHM,
        )

        self.auth_backend = AuthenticationBackend(
            name='cookie',
            transport=self.cookie_transport,
            get_strategy=lambda: self.jwt_strategy,
        )

    async def create_session(self, *, user: User) -> str:
        token = await self.jwt_strategy.write_token(user)
        return token

    async def create_access_token(self, *, user: User) -> str:
        """Create access token with custom user data in payload"""
        token = await self.jwt_strategy.write_token(user)
        return token


jwt_auth_service = JWTAuthService()


def get_jwt_strategy() -> JWTStrategy:
    return jwt_auth_service.jwt_strategy


auth_backend = jwt_auth_service.auth_backend

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)
current_active_verified_user = fastapi_users.current_user(active=True, verified=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
