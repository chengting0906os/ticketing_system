from typing import List, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


class ListEventsUseCase:
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
    async def get_by_seller(self, seller_id: int) -> List[EventTicketingAggregate]:
        """Get all events for a seller (excluding tickets for performance optimization)"""
        Logger.base.info(f'📋 [LIST_BY_SELLER] Loading events for seller {seller_id}')

        events = await self.event_ticketing_query_repo.list_events_by_seller(seller_id=seller_id)

        Logger.base.info(f'✅ [LIST_BY_SELLER] Found {len(events)} events for seller {seller_id}')
        return events

    @Logger.io
    async def list_available(self) -> List[EventTicketingAggregate]:
        """Get all available events (excluding tickets for performance optimization)"""
        Logger.base.info('🌟 [LIST_AVAILABLE] Loading all available events')

        events = await self.event_ticketing_query_repo.list_available_events()

        Logger.base.info(f'✅ [LIST_AVAILABLE] Found {len(events)} available events')
        return events
