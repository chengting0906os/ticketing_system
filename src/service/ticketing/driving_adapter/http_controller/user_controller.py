"""
Authentication Controller - 簡化版本，只有 login 和 create
"""

from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Cookie, Depends, Response, status
from opentelemetry import trace

from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_user_command_repo import IUserCommandRepo
from src.service.ticketing.app.interface.i_user_query_repo import IUserQueryRepo
from src.service.ticketing.app.query.user_query_use_case import UserUseCase
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.driving_adapter.http_controller.auth.jwt_auth import JwtAuth
from src.service.ticketing.driving_adapter.schema.user_schema import (
    CreateUserRequest,
    LoginRequest,
    UserResponse,
)


# === API Router ===

router = APIRouter()


@inject
async def get_current_user(
    jwt_auth: JwtAuth = Depends(Provide[Container.jwt_auth]),
    token: Optional[str] = Cookie(None, alias='fastapiusersauth'),
) -> UserEntity:
    """
    Get current user from JWT token (stateless, no DB query)

    This function is synchronous despite being marked async for FastAPI compatibility.
    No actual async operations are performed.
    """
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span('auth.get_current_user'):
        user = jwt_auth.get_current_user_info_from_jwt(token)
        trace.get_current_span().set_attributes(
            {
                'user.id': user.id or 0,
                'user.email': user.email,
                'user.role': user.role.value,
            }
        )
        return user


@router.post('', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@Logger.io
@inject
async def create_user(
    request: CreateUserRequest,
    user_command_repo: IUserCommandRepo = Depends(Provide[Container.user_command_repo]),
):
    # Create UserUseCase with injected command repo
    use_case = UserUseCase(user_command_repo=user_command_repo)
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
    user_query_repo: IUserQueryRepo = Depends(Provide[Container.user_query_repo]),
    jwt_auth: JwtAuth = Depends(Provide[Container.jwt_auth]),
):
    user_entity = await jwt_auth.authenticate_user(
        user_query_repo=user_query_repo,
        email=request.email,
        password=request.password.get_secret_value(),
    )

    token = jwt_auth.create_jwt_token(user_entity)

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
