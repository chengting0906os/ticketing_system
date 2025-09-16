from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_repo import BookingRepo
from src.booking.infra.booking_repo_impl import BookingRepoImpl
from src.event.domain.event_repo import EventRepo
from src.event.infra.event_repo_impl import EventRepoImpl
from src.shared.config.db_setting import get_async_session
from src.ticket.domain.ticket_repo import TicketRepo
from src.ticket.infra.ticket_repo_impl import TicketRepoImpl
from src.user.domain.user_repo import UserRepo
from src.user.infra.user_repo_impl import UserRepoImpl


def get_booking_repo(session: AsyncSession = Depends(get_async_session)) -> BookingRepo:
    return BookingRepoImpl(session)


def get_user_repo(session: AsyncSession = Depends(get_async_session)) -> UserRepo:
    return UserRepoImpl(session)


def get_ticket_repo(session: AsyncSession = Depends(get_async_session)) -> TicketRepo:
    return TicketRepoImpl(session)


def get_event_repo(session: AsyncSession = Depends(get_async_session)) -> EventRepo:
    return EventRepoImpl(session)
