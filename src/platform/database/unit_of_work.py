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

from src.platform.database.db_setting import get_async_read_session, get_async_session


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

    Supports dual session mode:
    - Writer session: For command repos (INSERT/UPDATE/DELETE)
    - Reader session: For query repos (SELECT) - routes to Aurora read replicas

    Usage in use case:
        async with uow:
            booking = await uow.booking_command_repo.create(booking=...)
            await uow.commit()
    """

    def __init__(self, writer_session: AsyncSession, reader_session: AsyncSession):
        """
        Initialize UnitOfWork with separate read/write sessions

        Args:
            writer_session: Session connected to writer endpoint (RDS Proxy)
            reader_session: Session connected to reader endpoint (read replicas)
        """
        self.session = writer_session  # For backward compatibility
        self.writer_session = writer_session
        self.reader_session = reader_session

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

        # Create repositories with appropriate sessions
        # Command repos use WRITER session
        self.booking_command_repo = IBookingCommandRepoImpl()
        self.booking_command_repo.session = self.writer_session

        # Query repos use READER session (read replicas)
        self.booking_query_repo = BookingQueryRepoImpl(session_factory=None)
        self.booking_query_repo.session = self.reader_session

        # Event/Ticket command repo uses raw SQL with asyncpg (no session needed)
        self.event_ticketing_command_repo = EventTicketingCommandRepoImpl()

        # Query repo uses READER session (read replicas)
        self.event_ticketing_query_repo = EventTicketingQueryRepoImpl(
            session_factory=None  # type: ignore
        )
        self.event_ticketing_query_repo.session = self.reader_session  # type: ignore

        return await super().__aenter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        # Note: session cleanup handled by get_async_session context manager

    async def _commit(self):
        """
        Commit writer session

        Note: Reader session is read-only, so only writer session needs commit
        """
        await self.writer_session.commit()

    async def rollback(self) -> None:
        """
        Rollback writer session

        Note: Reader session is read-only, so only writer session needs rollback
        """
        await self.writer_session.rollback()


def get_unit_of_work(
    writer_session: AsyncSession = Depends(get_async_session),
    reader_session: AsyncSession = Depends(get_async_read_session),
) -> AbstractUnitOfWork:
    """
    FastAPI dependency for Unit of Work with read/write splitting

    Provides dual sessions:
    - writer_session: Connected to Aurora writer (via RDS Proxy)
    - reader_session: Connected to Aurora read replicas

    Usage:
        async def create_booking(uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
            async with uow:
                # Command repos automatically use writer_session
                booking = await uow.booking_command_repo.create(...)
                # Query repos automatically use reader_session
                existing = await uow.booking_query_repo.get_by_id(booking_id=1)
                await uow.commit()
    """
    return SqlAlchemyUnitOfWork(writer_session, reader_session)
