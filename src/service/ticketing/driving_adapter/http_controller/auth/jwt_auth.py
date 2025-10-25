"""
User Authentication Service (Use Case Layer)
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
import jwt

from src.platform.config.core_setting import settings
from src.service.ticketing.app.interface.i_user_query_repo import IUserQueryRepo
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole


class JwtAuth:
    def __init__(self):
        self.secret = settings.SECRET_KEY.get_secret_value()
        self.algorithm = settings.ALGORITHM
        self.token_expire_days = 7

    def create_jwt_token(self, user_entity: UserEntity) -> str:
        payload = {
            'sub': str(user_entity.id),
            'exp': datetime.now(timezone.utc) + timedelta(days=self.token_expire_days),
            'iat': datetime.now(timezone.utc),
            'user_id': str(user_entity.id),  # Convert UUID to string for JWT
            'email': user_entity.email,
            'name': user_entity.name,
            'role': user_entity.role.value
            if hasattr(user_entity.role, 'value')
            else user_entity.role,
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

        # 解碼 token，取得所有用戶資訊
        payload = self.decode_jwt_token(token)

        # 驗證必要欄位
        user_id = payload.get('user_id')
        email = payload.get('email')
        name = payload.get('name')
        role = payload.get('role')
        is_active = payload.get('is_active')

        if not user_id or not email or not name or not role or is_active is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

        # 從 JWT payload 重建 UserEntity（不查 DB）
        user_entity = UserEntity(
            id=UUID(user_id)
            if isinstance(user_id, str)
            else user_id,  # Convert string back to UUID
            email=email,
            name=name,
            role=UserRole(role) if isinstance(role, str) else role,
            is_active=is_active,
        )

        # 驗證用戶狀態（基於 JWT payload）
        if not user_entity.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is inactive')

        return user_entity
