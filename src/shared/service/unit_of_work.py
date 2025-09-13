from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config.db_setting import get_async_session


if TYPE_CHECKING:
    from src.order.domain.order_repo import OrderRepo
    from src.event.domain.event_repo import EventRepo
    from src.user.domain.user_repo import UserRepo
    from src.ticket.domain.ticket_repo import TicketRepo


class AbstractUnitOfWork(abc.ABC):
    events: EventRepo
    orders: OrderRepo
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
        from src.order.infra.order_repo_impl import OrderRepoImpl
        from src.event.infra.event_repo_impl import EventRepoImpl
        from src.user.infra.user_repo_impl import UserRepoImpl
        from src.ticket.infra.ticket_repo_impl import TicketRepoImpl

        self.events = EventRepoImpl(self.session)
        self.orders = OrderRepoImpl(self.session)
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
