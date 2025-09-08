"""User routers."""

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.jwt_auth_service import auth_backend, fastapi_users
from src.user.domain.user_entity import UserRole
from src.user.port.user_schema import UserCreate, UserPublic, UserRead, UserUpdate
from src.user.use_case.manager import get_user_manager


auth_router = APIRouter()

users_router = APIRouter()
users_router.include_router(
    fastapi_users.get_users_router(
        UserRead,
        UserUpdate,
    ),
)


# Custom login endpoint that returns user data (must be defined before including default router)
@auth_router.post('/login', response_model=UserPublic)
@Logger.io
async def login(
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager=Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
):
    user = await user_manager.authenticate(credentials)

    if user is None or not user.is_active:
        raise DomainError('LOGIN_BAD_CREDENTIALS')

    #
    token = await strategy.write_token(user)

    #
    response.set_cookie(
        key='fastapiusersauth',
        value=token,
        max_age=3600,
        httponly=True,
        samesite='lax',
        secure=False,  # Set to True in production with HTTPS
    )

    return UserPublic(id=user.id, email=user.email, name=user.name, role=user.role)


@users_router.post('', response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@Logger.io
async def register_user(
    user_create: UserCreate,
    user_manager=Depends(get_user_manager),
):
    valid_roles = [role.value for role in UserRole]
    if user_create.role not in valid_roles:
        raise DomainError(
            f'Invalid role: {user_create.role}. Must be one of: {", ".join(valid_roles)}'
        )

    user = await user_manager.create(user_create, safe=True, request=None)
    return user
