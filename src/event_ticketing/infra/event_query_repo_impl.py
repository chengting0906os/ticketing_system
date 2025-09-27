from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.event_entity import Event, EventStatus
from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.event_ticketing.infra.event_model import EventModel
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.infra.user_model import UserModel


class EventQueryRepoImpl(EventQueryRepo):
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
    async def get_by_id(self, *, event_id: int) -> Optional[Event]:
        result = await self.session.execute(select(EventModel).where(EventModel.id == event_id))
        db_event = result.scalar_one_or_none()

        if not db_event:
            return None

        return EventQueryRepoImpl._to_entity(db_event)

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
        event = EventQueryRepoImpl._to_entity(db_event)

        return event, user

    @Logger.io
    async def get_by_seller(self, *, seller_id: int) -> List[Event]:
        result = await self.session.execute(
            select(EventModel).where(EventModel.seller_id == seller_id).order_by(EventModel.id)
        )
        db_events = result.scalars().all()

        return [EventQueryRepoImpl._to_entity(db_event) for db_event in db_events]

    @Logger.io(truncate_content=True)
    async def list_available(self) -> List[Event]:
        result = await self.session.execute(
            select(EventModel)
            .where(EventModel.is_active)
            .where(EventModel.status == EventStatus.AVAILABLE.value)
            .order_by(EventModel.id)
        )
        db_events = result.scalars().all()

        return [EventQueryRepoImpl._to_entity(db_event) for db_event in db_events]
