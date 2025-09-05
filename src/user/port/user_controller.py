"""User routers."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions

from src.user.infra.auth import auth_backend, fastapi_users
from src.user.port.user_schema import UserCreate, UserRead, UserUpdate, UserPublic
from src.user.use_case.manager import get_user_manager
from src.user.domain.user_model import UserRole


auth_router = APIRouter()

# Custom login endpoint that returns user data (must be defined before including default router)
@auth_router.post("/login", response_model=UserPublic)
async def login(
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager=Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
):
    """Custom login endpoint that returns user data with JWT cookie."""
    user = await user_manager.authenticate(credentials)
    
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS",
        )
    
    # Generate JWT token
    token = await strategy.write_token(user)
    
    # Set cookie
    response.set_cookie(
        key="fastapiusersauth",
        value=token,
        max_age=3600,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production with HTTPS
    )
    
    # Return user data
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role
    )


# Don't include the default auth router to avoid conflicts
# auth_router.include_router(
#     fastapi_users.get_auth_router(auth_backend),
# )

users_router = APIRouter()
users_router.include_router(
    fastapi_users.get_users_router(
        UserRead,
        UserUpdate,
    ),
)

# Custom registration endpoint to match BDD requirements
@users_router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_create: UserCreate,
    user_manager=Depends(get_user_manager),
):
    """Register a new user."""
    # Domain validation: Check if role is valid
    valid_roles = [role.value for role in UserRole]
    if user_create.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {user_create.role}. Must be one of: {', '.join(valid_roles)}"
        )
    
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
