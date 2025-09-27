from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_query_repo import BookingQueryRepo

# Combined repo implementation will be created by inheriting from command and query
from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl
from src.booking.infra.booking_query_repo_impl import BookingQueryRepoImpl
from src.event_ticketing.domain.event_command_repo import EventCommandRepo
from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.event_ticketing.domain.ticket_command_repo import TicketCommandRepo
from src.event_ticketing.domain.ticket_query_repo import TicketQueryRepo
from src.event_ticketing.infra.event_command_repo_impl import EventCommandRepoImpl
from src.event_ticketing.infra.event_query_repo_impl import EventQueryRepoImpl
from src.event_ticketing.infra.ticket_command_repo_impl import TicketCommandRepoImpl
from src.event_ticketing.infra.ticket_query_repo_impl import TicketQueryRepoImpl
from src.shared.config.db_setting import get_async_session
from src.shared_kernel.user.domain.user_command_repo import UserCommandRepo
from src.shared_kernel.user.domain.user_query_repo import UserQueryRepo
from src.shared_kernel.user.domain.user_repo import UserRepo
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl
from src.shared_kernel.user.infra.user_query_repo_impl import UserQueryRepoImpl
from src.shared_kernel.user.infra.user_repo_impl import UserRepoImpl


def get_booking_command_repo(
    session: AsyncSession = Depends(get_async_session),
) -> BookingCommandRepo:
    return BookingCommandRepoImpl(session)


def get_booking_query_repo(session: AsyncSession = Depends(get_async_session)) -> BookingQueryRepo:
    return BookingQueryRepoImpl(session)


def get_user_repo(session: AsyncSession = Depends(get_async_session)) -> UserRepo:
    return UserRepoImpl(session)


def get_user_command_repo(session: AsyncSession = Depends(get_async_session)) -> UserCommandRepo:
    return UserCommandRepoImpl(session)


def get_user_query_repo(session: AsyncSession = Depends(get_async_session)) -> UserQueryRepo:
    return UserQueryRepoImpl(session)


def get_event_command_repo(session: AsyncSession = Depends(get_async_session)) -> EventCommandRepo:
    return EventCommandRepoImpl(session)


def get_event_query_repo(session: AsyncSession = Depends(get_async_session)) -> EventQueryRepo:
    return EventQueryRepoImpl(session)


def get_ticket_command_repo(
    session: AsyncSession = Depends(get_async_session),
) -> TicketCommandRepo:
    return TicketCommandRepoImpl(session)


def get_ticket_query_repo(session: AsyncSession = Depends(get_async_session)) -> TicketQueryRepo:
    return TicketQueryRepoImpl(session)
