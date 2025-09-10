"""JWT implementation of authentication service."""

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from src.shared.config.core_setting import settings
from src.user.domain.user_model import User
from src.user.use_case.manager import get_user_manager


class JWTAuthService:
    def __init__(self):
        self.cookie_transport = CookieTransport(
            cookie_name='fastapiusersauth',
            cookie_max_age=3600,
            cookie_secure=False,  # Set to True in production with HTTPS
            cookie_httponly=True,
            cookie_samesite='lax',
        )

        self.jwt_strategy = JWTStrategy(
            secret=settings.SECRET_KEY.get_secret_value(),
            lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            algorithm=settings.ALGORITHM,
        )

        self.auth_backend = AuthenticationBackend(
            name='cookie',
            transport=self.cookie_transport,
            get_strategy=lambda: self.jwt_strategy,
        )

    async def create_session(self, user: User) -> str:
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
