"""
User Authentication Service (Use Case Layer)
"""

from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import HTTPException, status
import jwt

from src.shared.config.core_setting import settings
from src.shared_kernel.user.domain.user_entity import UserEntity
from src.shared_kernel.user.domain.user_repo import UserRepo


class AuthService:
    def __init__(self):
        self.secret = settings.SECRET_KEY.get_secret_value()
        self.algorithm = settings.ALGORITHM
        self.token_expire_days = 7

    def create_jwt_token(self, user_entity: UserEntity) -> str:
        payload = {
            #
            'sub': str(user_entity.id),
            'exp': datetime.now(timezone.utc) + timedelta(days=self.token_expire_days),
            'iat': datetime.now(timezone.utc),
            #
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

    async def authenticate_user(self, user_repo: UserRepo, email: str, password: str) -> UserEntity:
        user_entity = await user_repo.verify_password(email, password)
        validated_user = UserEntity.validate_user_exists(user_entity)
        validated_user.validate_active()

        return validated_user


# 全域實例
auth_service = AuthService()
