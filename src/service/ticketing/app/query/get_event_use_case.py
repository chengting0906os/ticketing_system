from typing import Optional, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate


class GetEventUseCase:
    def __init__(self, event_ticketing_query_repo: IEventTicketingQueryRepo) -> None:
        self.event_ticketing_query_repo = event_ticketing_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        event_ticketing_query_repo: IEventTicketingQueryRepo = Depends(
            Provide[Container.event_ticketing_query_repo]
        ),
    ) -> Self:
        return cls(event_ticketing_query_repo=event_ticketing_query_repo)

    @Logger.io
    async def get_by_id(self, *, event_id: int) -> Optional[EventTicketingAggregate]:
        """Get event aggregate by ID with tickets."""
        Logger.base.info(f'🎫 [GET_EVENT] Loading event {event_id}')

        event_aggregate = (
            await self.event_ticketing_query_repo.get_event_aggregate_by_id_with_tickets(
                event_id=event_id
            )
        )

        if event_aggregate is None:
            Logger.base.warning(f'⚠️ [GET_EVENT] Event {event_id} not found')
            return None

        Logger.base.info(f'✅ [GET_EVENT] Found event {event_id}')
        return event_aggregate
