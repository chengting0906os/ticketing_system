from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.event_ticketing.domain.event_entity import Event
from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.shared.config.di import Container
from src.shared.logging.loguru_io import Logger


class ListEventsUseCase:
    def __init__(self, event_repo: EventQueryRepo):
        self.event_repo = event_repo

    @classmethod
    @inject
    def depends(cls, event_repo: EventQueryRepo = Depends(Provide[Container.event_query_repo])):
        return cls(event_repo=event_repo)

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[Event]:
        events = await self.event_repo.get_by_seller(seller_id=seller_id)
        return events

    @Logger.io(truncate_content=True)
    async def list_available(self) -> List[Event]:
        events = await self.event_repo.list_available()
        return events
