from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.platform.database.db_setting import Base


if TYPE_CHECKING:
    from src.service.ticketing.driven_adapter.model.event_model import EventModel
    from src.service.ticketing.driven_adapter.model.ticket_model import TicketModel
    from src.service.ticketing.driven_adapter.model.user_model import UserModel


class BookingModel(Base):
    __tablename__ = 'booking'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'))
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey('event.id'))
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

    # Relationships
    buyer: Mapped['UserModel'] = relationship('UserModel', foreign_keys=[buyer_id], lazy='selectin')
    event: Mapped['EventModel'] = relationship(
        'EventModel', foreign_keys=[event_id], lazy='selectin'
    )
    tickets: Mapped[list['TicketModel']] = relationship(
        'TicketModel',
        secondary='booking_ticket_mapping',
        back_populates='bookings',
        lazy='selectin',
    )
