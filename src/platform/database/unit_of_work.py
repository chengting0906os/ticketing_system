"""
Unit of Work Pattern - 統一管理 database session 和 repositories

Architecture:
- UoW 負責 session 生命週期管理
- UoW 負責 commit/rollback
- Repositories 透過 UoW 取得 shared session
- Use cases 透過 UoW 協調多個 repositories
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.database.db_setting import get_async_session


if TYPE_CHECKING:
    from src.service.ticketing.app.interface.i_booking_command_repo import (
        IBookingCommandRepo,
    )
    from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
    from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
        IEventTicketingCommandRepo,
    )
    from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
        IEventTicketingQueryRepo,
    )


class AbstractUnitOfWork(abc.ABC):
    """
    Abstract Unit of Work for Ticketing Service

    Responsibilities:
    - Manage database session lifecycle
    - Coordinate transactions across multiple repositories
    - Provide commit/rollback interface

    Usage:
        async with uow:
            booking = await uow.booking_command_repo.create(...)
            await uow.commit()
    """

    # Booking repositories
    booking_command_repo: IBookingCommandRepo
    booking_query_repo: IBookingQueryRepo

    # Event/Ticket repositories
    event_ticketing_command_repo: IEventTicketingCommandRepo
    event_ticketing_query_repo: IEventTicketingQueryRepo

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args):
        await self.rollback()

    async def commit(self):
        """Commit the transaction"""
        await self._commit()

    @abc.abstractmethod
    async def _commit(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """
    SQLAlchemy implementation of Unit of Work

    Usage in use case:
        async with uow:
            booking = await uow.booking_command_repo.create(booking=...)
            await uow.commit()
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        from src.service.ticketing.driven_adapter.repo.booking_command_repo_impl import (
            IBookingCommandRepoImpl,
        )
        from src.service.ticketing.driven_adapter.repo.booking_query_repo_impl import (
            BookingQueryRepoImpl,
        )
        from src.service.ticketing.driven_adapter.repo.event_ticketing_command_repo_impl import (
            EventTicketingCommandRepoImpl,
        )
        from src.service.ticketing.driven_adapter.repo.event_ticketing_query_repo_impl import (
            EventTicketingQueryRepoImpl,
        )

        # Create repositories with shared session
        # Booking repos
        self.booking_command_repo = IBookingCommandRepoImpl()
        self.booking_command_repo.session = self.session
        self.booking_query_repo = BookingQueryRepoImpl(session_factory=None)
        self.booking_query_repo.session = self.session  # Inject session for UoW mode

        # Event/Ticket repos
        self.event_ticketing_command_repo = EventTicketingCommandRepoImpl(
            session_factory=None  # type: ignore
        )
        self.event_ticketing_command_repo.session = self.session  # type: ignore
        self.event_ticketing_query_repo = EventTicketingQueryRepoImpl(
            session_factory=None  # type: ignore
        )
        self.event_ticketing_query_repo.session = self.session  # type: ignore

        return await super().__aenter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        # Note: session cleanup handled by get_async_session context manager

    async def _commit(self):
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def get_unit_of_work(
    session: AsyncSession = Depends(get_async_session),
) -> AbstractUnitOfWork:
    """
    FastAPI dependency for Unit of Work

    Usage:
        async def create_booking(uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
            async with uow:
                booking = await uow.booking_command_repo.create(...)
                await uow.commit()
    """
    return SqlAlchemyUnitOfWork(session)
