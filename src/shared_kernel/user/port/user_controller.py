"""
Authentication Controller - 簡化版本，只有 login 和 create
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_user_repo
from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.domain.user_repo import UserRepo
from src.shared_kernel.user.port.user_schema import CreateUserRequest, LoginRequest, UserResponse
from src.shared_kernel.user.use_case.auth_service import auth_service
from src.shared_kernel.user.use_case import user_use_case


# === API Router ===

router = APIRouter()


@router.post('', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_user(request: CreateUserRequest, user_repo: UserRepo = Depends(get_user_repo)):
    """創建新用戶"""
    try:
        # 驗證角色
        valid_roles = [role.value for role in UserRole]
        if request.role not in valid_roles:
            raise DomainError(
                f'Invalid role: {request.role}. Must be one of: {", ".join(valid_roles)}'
            )

        # 創建用戶
        user_entity = await user_use_case.create_user(
            user_repo=user_repo,
            email=request.email,
            password=request.password,
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

    except HTTPException:
        raise
    except Exception as e:
        Logger.base.error(f'創建用戶失敗: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to create user'
        )


@router.post('/login', response_model=UserResponse)
@Logger.io
async def login(
    response: Response, request: LoginRequest, user_repo: UserRepo = Depends(get_user_repo)
):
    try:
        user_entity = await auth_service.authenticate_user(
            user_repo=user_repo, email=request.email, password=request.password
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

    except DomainError as e:
        Logger.base.error(f'登入失敗: {e}')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='LOGIN_BAD_CREDENTIALS')
    except HTTPException:
        raise
    except Exception as e:
        Logger.base.error(f'登入失敗: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Login failed'
        )


# === 依賴注入：取得當前用戶 ===


async def get_current_user(
    user_repo: UserRepo = Depends(get_user_repo), fastapiusersauth: Optional[str] = Cookie(None)
) -> UserEntity:
    """從 Cookie 中取得當前用戶"""
    if not fastapiusersauth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')

    try:
        # 解碼 token
        payload = auth_service.decode_jwt_token(fastapiusersauth)
        user_id = payload.get('user_id')

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

        # 取得用戶 - validation logic now handled in use case layer
        user_entity = await user_use_case.get_user_by_id(user_repo, user_id)

        return user_entity

    except HTTPException:
        raise
    except Exception as e:
        Logger.base.error(f'認證失敗: {e}')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication failed'
        )


@router.get('', response_model=UserResponse)
async def get_me(current_user: UserEntity = Depends(get_current_user)):
    """取得當前用戶資料"""
    return UserResponse(
        id=current_user.id or 0,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        is_active=current_user.is_active,
    )
