from datetime import datetime
from typing import TYPE_CHECKING, Optional
from pydantic import UUID7 as UUID

from sqlalchemy import ARRAY, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.platform.database.db_setting import Base


if TYPE_CHECKING:
    from src.service.ticketing.driven_adapter.model.event_model import EventModel
    from src.service.ticketing.driven_adapter.model.user_model import UserModel


class BookingModel(Base):
    __tablename__ = 'booking'

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)  # UUID7
    buyer_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    section: Mapped[str] = mapped_column(String(10), nullable=False)
    subsection: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_positions: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='processing', nullable=False)
    seat_selection_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    buyer: Mapped['UserModel'] = relationship(
        'UserModel',
        primaryjoin='BookingModel.buyer_id == foreign(UserModel.id)',
        foreign_keys='[BookingModel.buyer_id]',
        viewonly=True,
        lazy='selectin',
    )
    event: Mapped['EventModel'] = relationship(
        'EventModel',
        primaryjoin='BookingModel.event_id == foreign(EventModel.id)',
        foreign_keys='[BookingModel.event_id]',
        viewonly=True,
        lazy='selectin',
    )
