"""
User Authentication Service (Use Case Layer)
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import HTTPException, status
import jwt

from src.platform.config.core_setting import settings
from src.service.ticketing.app.interface.i_user_query_repo import IUserQueryRepo
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole


class JwtAuth:
    def __init__(self) -> None:
        self.secret = settings.SECRET_KEY.get_secret_value()
        self.algorithm = settings.ALGORITHM
        self.token_expire_days = 7

    def create_jwt_token(self, user_entity: UserEntity) -> str:
        payload = {
            'sub': str(user_entity.id),
            'exp': datetime.now(timezone.utc) + timedelta(days=self.token_expire_days),
            'iat': datetime.now(timezone.utc),
            'user_id': user_entity.id,
            'email': user_entity.email,
            'name': user_entity.name,
            'role': user_entity.role,
            'is_active': user_entity.is_active,
        }

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode_jwt_token(self, token: str) -> Dict:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

    async def authenticate_user(
        self, user_query_repo: IUserQueryRepo, email: str, password: str
    ) -> UserEntity:
        user_entity = await user_query_repo.verify_password(email=email, plain_password=password)
        validated_user = UserEntity.validate_user_exists(user_entity)
        validated_user.validate_active()

        return validated_user

    def get_current_user_info_from_jwt(self, token: Optional[str]) -> UserEntity:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated'
            )

        # Decode token, get all user information
        payload = self.decode_jwt_token(token)

        # Validate required fields
        user_id = payload.get('user_id')
        email = payload.get('email')
        name = payload.get('name')
        role = payload.get('role')
        is_active = payload.get('is_active')

        if not user_id or not email or not name or not role or is_active is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

        # Rebuild UserEntity from JWT payload (no DB query)
        user_entity = UserEntity(
            id=user_id,
            email=email,
            name=name,
            role=UserRole(role),
            is_active=is_active,
        )

        # Validate user status (based on JWT payload)
        if not user_entity.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is inactive')

        return user_entity
