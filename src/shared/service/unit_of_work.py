from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, List

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config.db_setting import get_async_session
from src.shared.logging.loguru_io import Logger


if TYPE_CHECKING:
    from src.event_ticketing.domain.event_repo import EventRepo
    from src.event_ticketing.domain.ticket_repo import TicketRepo
    from src.shared_kernel.user.domain.user_repo import UserRepo


class AbstractUnitOfWork(abc.ABC):
    events: EventRepo
    users: UserRepo
    tickets: TicketRepo

    def __init__(self):
        self.domain_events: List[Any] = []

    def collect_events(self, *aggregates):
        """Collect domain events from aggregates"""
        for aggregate in aggregates:
            if hasattr(aggregate, 'domain_events'):
                self.domain_events.extend(aggregate.domain_events)
                aggregate.clear_events()

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args):
        await self.rollback()

    async def commit(self):
        await self._commit()
        await self._publish_events()

    async def _publish_events(self):
        """Publish collected domain events after successful commit"""
        if self.domain_events:
            from src.shared.event_bus.event_publisher import get_event_publisher

            publisher = get_event_publisher()

            for event in self.domain_events:
                try:
                    # Determine topic based on event type
                    event_type = event.__class__.__name__.replace('Event', '').lower()
                    topic = f'ticketing-{event_type}'

                    await publisher.publish(event, topic)  # type: ignore
                except Exception as e:
                    # Log error but don't fail the transaction
                    Logger.base.error(f'Failed to publish event {event.__class__.__name__}: {e}')  # type: ignore

            # Clear events after publishing
            self.domain_events.clear()

    @abc.abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self):
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session: AsyncSession):
        super().__init__()
        self.session = session

    async def __aenter__(self):
        from src.event_ticketing.infra.event_repo_impl import EventRepoImpl
        from src.event_ticketing.infra.ticket_repo_impl import TicketRepoImpl
        from src.shared_kernel.user.infra.user_repo_impl import UserRepoImpl

        self.events = EventRepoImpl(self.session)
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
