from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import EventTicketingQueryRepo
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


class ListEventsUseCase:
    def __init__(self, event_ticketing_query_repo: EventTicketingQueryRepo):
        self.event_ticketing_query_repo = event_ticketing_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        event_ticketing_query_repo: EventTicketingQueryRepo = Depends(
            Provide[Container.event_ticketing_query_repo]
        ),
    ):
        return cls(event_ticketing_query_repo=event_ticketing_query_repo)

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[EventTicketingAggregate]:
        """獲取賣家的所有活動（不含票務，性能優化）"""
        Logger.base.info(f'📋 [LIST_BY_SELLER] Loading events for seller {seller_id}')

        events = await self.event_ticketing_query_repo.list_events_by_seller(seller_id=seller_id)

        Logger.base.info(f'✅ [LIST_BY_SELLER] Found {len(events)} events for seller {seller_id}')
        return events

    @Logger.io
    async def list_available(self) -> List[EventTicketingAggregate]:
        """獲取所有可用活動（不含票務，性能優化）"""
        Logger.base.info('🌟 [LIST_AVAILABLE] Loading all available events')

        events = await self.event_ticketing_query_repo.list_available_events()

        Logger.base.info(f'✅ [LIST_AVAILABLE] Found {len(events)} available events')
        return events
