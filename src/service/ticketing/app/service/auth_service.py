"""
User Authentication Service (Use Case Layer)
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import HTTPException, status
import jwt

from src.platform.config.core_setting import settings
from src.service.ticketing.app.query.user_query_use_case import UserUseCase
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.app.interface.i_user_query_repo import IUserQueryRepo


class AuthService:
    def __init__(self):
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

    async def get_current_user(
        self, user_query_repo: IUserQueryRepo, token: Optional[str]
    ) -> UserEntity:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated'
            )

        # 解碼 token
        payload = self.decode_jwt_token(token)
        user_id = payload.get('user_id')

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

        # 取得用戶 - 創建 UserUseCase 實例並注入 user_query_repo
        use_case = UserUseCase(user_query_repo=user_query_repo)
        user_entity = await use_case.get_user_by_id(user_id)

        # 驗證用戶
        if not user_entity:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')

        if not user_entity.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is inactive')

        return user_entity
