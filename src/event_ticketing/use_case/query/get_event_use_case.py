from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.event_ticketing.domain.event_entity import Event
from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.shared.config.di import Container
from src.shared.logging.loguru_io import Logger


class GetEventUseCase:
    def __init__(self, event_repo: EventQueryRepo):
        self.event_repo = event_repo

    @classmethod
    @inject
    def depends(cls, event_repo: EventQueryRepo = Depends(Provide[Container.event_query_repo])):
        return cls(event_repo=event_repo)

    @Logger.io
    async def get_by_id(self, event_id: int) -> Optional[Event]:
        event = await self.event_repo.get_by_id(event_id=event_id)
        return event
