from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config.db_setting import get_async_session


if TYPE_CHECKING:
    from src.booking.domain.booking_repo import BookingRepo
    from src.event.domain.event_repo import EventRepo
    from src.event.domain.ticket_repo import TicketRepo
    from src.user.domain.user_repo import UserRepo


class AbstractUnitOfWork(abc.ABC):
    events: EventRepo
    bookings: BookingRepo
    users: UserRepo
    tickets: TicketRepo

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args):
        await self.rollback()

    async def commit(self):
        await self._commit()

    @abc.abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self):
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        from src.booking.infra.booking_repo_impl import BookingRepoImpl
        from src.event.infra.event_repo_impl import EventRepoImpl
        from src.event.infra.ticket_repo_impl import TicketRepoImpl
        from src.user.infra.user_repo_impl import UserRepoImpl

        self.events = EventRepoImpl(self.session)
        self.bookings = BookingRepoImpl(self.session)
        self.users = UserRepoImpl(self.session)
        self.tickets = TicketRepoImpl(self.session)
        return await super().__aenter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.session.close()

    async def _commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()


def get_unit_of_work(session: AsyncSession = Depends(get_async_session)) -> AbstractUnitOfWork:
    return SqlAlchemyUnitOfWork(session)
