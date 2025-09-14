from typing import Dict, List, Optional

from fastapi import Depends

from src.event.domain.event_entity import Event
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CreateEventUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def create(
        self,
        name: str,
        description: str,
        price: int,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> Event:
        async with self.uow:
            event = Event.create(
                name=name,
                description=description,
                price=price,
                seller_id=seller_id,
                venue_name=venue_name,
                seating_config=seating_config,
                is_active=is_active,
            )

            created_event = await self.uow.events.create(event=event)
            await self.uow.commit()
        # raise Exception('Simulated error for testing rollback')  # --- IGNORE ---
        return created_event


class UpdateEventUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def update(
        self,
        event_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[int] = None,
        venue_name: Optional[str] = None,
        seating_config: Optional[Dict] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Event]:
        async with self.uow:
            # Get existing event
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                return None

            # Update only provided fields
            if name is not None:
                event.name = name
            if description is not None:
                event.description = description
            if price is not None:
                event.price = price
            if venue_name is not None:
                event.venue_name = venue_name
            if seating_config is not None:
                event.seating_config = seating_config
            if is_active is not None:
                event.is_active = is_active

            updated_event = await self.uow.events.update(event=event)
            await self.uow.commit()

        return updated_event


class GetEventUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def get_by_id(self, event_id: int) -> Optional[Event]:
        async with self.uow:
            event = await self.uow.events.get_by_id(event_id=event_id)
        return event


class ListEventsUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[Event]:
        async with self.uow:
            events = await self.uow.events.get_by_seller(seller_id=seller_id)
        return events

    @Logger.io
    async def list_available(self) -> List[Event]:
        async with self.uow:
            events = await self.uow.events.list_available()
        return events
