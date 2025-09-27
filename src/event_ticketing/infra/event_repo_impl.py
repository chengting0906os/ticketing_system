from typing import List, Optional

from sqlalchemy import delete as sql_delete, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.event_entity import Event, EventStatus
from src.event_ticketing.domain.event_repo import EventRepo
from src.event_ticketing.infra.event_model import EventModel
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.infra.user_model import UserModel


class EventRepoImpl(EventRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_event: EventModel) -> Event:
        return Event(
            name=db_event.name,
            description=db_event.description,
            seller_id=db_event.seller_id,
            venue_name=db_event.venue_name,
            seating_config=db_event.seating_config,
            is_active=db_event.is_active,
            status=EventStatus(db_event.status),
            id=db_event.id,
        )

    @Logger.io
    async def create(self, *, event: Event) -> Event:
        db_event = EventModel(
            name=event.name,
            description=event.description,
            seller_id=event.seller_id,
            venue_name=event.venue_name,
            seating_config=event.seating_config,
            is_active=event.is_active,
            status=event.status.value,  # Convert enum to string
        )
        self.session.add(db_event)
        await self.session.flush()
        await self.session.refresh(db_event)

        return EventRepoImpl._to_entity(db_event)

    @Logger.io
    async def get_by_id(self, *, event_id: int) -> Optional[Event]:
        result = await self.session.execute(select(EventModel).where(EventModel.id == event_id))
        db_event = result.scalar_one_or_none()

        if not db_event:
            return None

        return EventRepoImpl._to_entity(db_event)

    @Logger.io
    async def get_by_id_with_seller(
        self, *, event_id: int
    ) -> tuple[Optional[Event], Optional[UserModel]]:
        result = await self.session.execute(
            select(EventModel, UserModel)
            .join(UserModel, EventModel.seller_id == UserModel.id)
            .where(EventModel.id == event_id)
        )
        row = result.first()

        if not row:
            return None, None

        db_event, user = row
        event = EventRepoImpl._to_entity(db_event)

        return event, user

    @Logger.io
    async def update(self, *, event: Event) -> Event:
        stmt = (
            sql_update(EventModel)
            .where(EventModel.id == event.id)
            .values(
                name=event.name,
                description=event.description,
                venue_name=event.venue_name,
                seating_config=event.seating_config,
                is_active=event.is_active,
                status=event.status.value,
            )
            .returning(EventModel)
        )

        result = await self.session.execute(stmt)
        db_event = result.scalar_one_or_none()

        if not db_event:
            raise ValueError(f'Event with id {event.id} not found')

        return EventRepoImpl._to_entity(db_event)

    @Logger.io
    async def delete(self, *, event_id: int) -> bool:
        stmt = sql_delete(EventModel).where(EventModel.id == event_id).returning(EventModel.id)

        result = await self.session.execute(stmt)
        deleted_id = result.scalar_one_or_none()

        return deleted_id is not None

    @Logger.io
    async def get_by_seller(self, *, seller_id: int) -> List[Event]:
        result = await self.session.execute(
            select(EventModel).where(EventModel.seller_id == seller_id).order_by(EventModel.id)
        )
        db_events = result.scalars().all()

        return [EventRepoImpl._to_entity(db_event) for db_event in db_events]

    @Logger.io(truncate_content=True)
    async def list_available(self) -> List[Event]:
        result = await self.session.execute(
            select(EventModel)
            .where(EventModel.is_active)
            .where(EventModel.status == EventStatus.AVAILABLE.value)
            .order_by(EventModel.id)
        )
        db_events = result.scalars().all()

        return [EventRepoImpl._to_entity(db_event) for db_event in db_events]

    @Logger.io
    async def release_event_atomically(self, *, event_id: int) -> Event:
        # This method is no longer needed since events don't have RESERVED status
        # Events are either AVAILABLE, SOLD_OUT, or ENDED
        stmt = (
            sql_update(EventModel)
            .where(EventModel.id == event_id)
            .values(status=EventStatus.AVAILABLE.value)
            .returning(EventModel)
        )

        result = await self.session.execute(stmt)
        db_event = result.scalar_one_or_none()

        if not db_event:
            raise DomainError('Unable to update event status')

        return EventRepoImpl._to_entity(db_event)
