from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.event_ticketing.domain.event_ticketing_aggregate import EventTicketingAggregate
from src.event_ticketing.domain.event_ticketing_query_repo import EventTicketingQueryRepo
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


class GetEventUseCase:
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
    async def get_by_id(self, event_id: int) -> Optional[EventTicketingAggregate]:
        """獲取活動聚合根（不含票務，性能優化）"""
        Logger.base.info(f'🔍 [GET_EVENT] Loading event aggregate for event {event_id}')

        event_aggregate = await self.event_ticketing_query_repo.get_event_aggregate_by_id(
            event_id=event_id
        )

        if event_aggregate:
            Logger.base.info(
                f'✅ [GET_EVENT] Found event {event_id}: {event_aggregate.event.name} '
                f'with {event_aggregate.total_tickets_count} tickets'
            )
        else:
            Logger.base.warning(f'❌ [GET_EVENT] Event {event_id} not found')

        return event_aggregate
