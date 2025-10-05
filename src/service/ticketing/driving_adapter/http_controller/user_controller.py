"""
Authentication Controller - 簡化版本，只有 login 和 create
"""

from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Cookie, Depends, Response, status

from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.service.auth_service import AuthService
from src.service.ticketing.app.query.user_query_use_case import UserUseCase
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.app.interface.i_user_repo import UserRepo
from src.service.ticketing.driving_adapter.schema.user_schema import (
    CreateUserRequest,
    LoginRequest,
    UserResponse,
)


# === API Router ===

router = APIRouter()


@inject
async def get_current_user(
    user_repo: UserRepo = Depends(Provide[Container.user_repo]),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
    token: Optional[str] = Cookie(None, alias='fastapiusersauth'),
) -> UserEntity:
    return await auth_service.get_current_user(user_repo, token)


@router.post('', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@Logger.io
@inject
async def create_user(
    request: CreateUserRequest, user_repo: UserRepo = Depends(Provide[Container.user_repo])
):
    # Create UserUseCase with injected repo
    use_case = UserUseCase(user_repo=user_repo)
    user_entity = await use_case.create_user(
        email=request.email,
        password=request.password.get_secret_value(),
        name=request.name,
        role=request.role,
    )

    return UserResponse(
        id=user_entity.id or 0,
        email=user_entity.email,
        name=user_entity.name,
        role=user_entity.role,
        is_active=user_entity.is_active,
    )


@router.post('/login', response_model=UserResponse)
@Logger.io
@inject
async def login(
    response: Response,
    request: LoginRequest,
    user_repo: UserRepo = Depends(Provide[Container.user_repo]),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    user_entity = await auth_service.authenticate_user(
        user_repo=user_repo, email=request.email, password=request.password.get_secret_value()
    )

    token = auth_service.create_jwt_token(user_entity)

    response.set_cookie(
        key='fastapiusersauth',
        value=token,
        max_age=7 * 24 * 60 * 60,  # 7 天
        httponly=True,
        samesite='lax',
        secure=False,  # 生產環境設為 True
    )

    return UserResponse(
        id=user_entity.id or 0,
        email=user_entity.email,
        name=user_entity.name,
        role=user_entity.role,
        is_active=user_entity.is_active,
    )


@router.get('', response_model=UserResponse)
@Logger.io
async def get_me(current_user: UserEntity = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id or 0,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        is_active=current_user.is_active,
    )
