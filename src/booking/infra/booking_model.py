from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.shared.config.db_setting import Base


if TYPE_CHECKING:
    from src.event_ticketing.infra.event_model import EventModel
    from src.user.domain.user_model import User


class BookingModel(Base):
    __tablename__ = 'booking'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'))
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey('event.id'))
    ticket_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=[])
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='processing', nullable=False)
    seat_selection_mode: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    buyer: Mapped['User'] = relationship('User', foreign_keys=[buyer_id], lazy='select')
    event: Mapped['EventModel'] = relationship('EventModel', foreign_keys=[event_id], lazy='select')
