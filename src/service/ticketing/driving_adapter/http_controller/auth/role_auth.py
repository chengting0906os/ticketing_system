from fastapi import Depends
from opentelemetry import trace

from src.platform.exception.exceptions import ForbiddenError
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.driving_adapter.http_controller.user_controller import (
    get_current_user as get_user_from_controller,
)


class RoleAuthStrategy:
    @staticmethod
    def can_create_event(user: UserEntity) -> bool:
        return user.role == UserRole.SELLER

    @staticmethod
    def can_create_booking(user: UserEntity) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    def is_buyer(user: UserEntity) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    def is_seller(user: UserEntity) -> bool:
        return user.role == UserRole.SELLER


async def get_current_user(
    current_user: UserEntity = Depends(get_user_from_controller),
) -> UserEntity:
    return current_user


async def require_buyer(current_user: UserEntity = Depends(get_user_from_controller)) -> UserEntity:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(
        'auth.require_buyer',
        attributes={
            'user.id': current_user.id or 0,
            'user.role': current_user.role.value,
        },
    ):
        if not RoleAuthStrategy.can_create_booking(current_user):
            raise ForbiddenError('Only buyers can perform this action')
        return current_user


async def require_seller(
    current_user: UserEntity = Depends(get_user_from_controller),
) -> UserEntity:
    if not RoleAuthStrategy.can_create_event(current_user):
        raise ForbiddenError('Only sellers can perform this action')
    return current_user


async def require_buyer_or_seller(
    current_user: UserEntity = Depends(get_user_from_controller),
) -> UserEntity:
    if current_user.role not in [UserRole.BUYER, UserRole.SELLER]:
        raise ForbiddenError("You don't have permission to perform this action")
    return current_user
