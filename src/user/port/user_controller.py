"""User routers."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users import exceptions

from src.user.infra.auth import auth_backend, fastapi_users
from src.user.domain.user_schema import UserCreate, UserRead, UserUpdate
from src.user.use_case.manager import get_user_manager


auth_router = APIRouter()
auth_router.include_router(
    fastapi_users.get_auth_router(auth_backend),
)

users_router = APIRouter()
users_router.include_router(
    fastapi_users.get_users_router(
        UserRead,
        UserUpdate,
    ),
)

# Custom registration endpoint to match BDD requirements
@users_router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_create: UserCreate,
    user_manager=Depends(get_user_manager),
):
    """Register a new user."""
    try:
        user = await user_manager.create(
            user_create, safe=True, request=None
        )
        return user
    except exceptions.UserAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_USER_ALREADY_EXISTS",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
