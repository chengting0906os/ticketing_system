from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.platform.database.db_setting import Base


if TYPE_CHECKING:
    from src.service.ticketing.driven_adapter.model.booking_model import BookingModel


class TicketModel(Base):
    __tablename__ = 'ticket'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey('event.id'), nullable=False)
    section: Mapped[str] = mapped_column(String(10), nullable=False)
    subsection: Mapped[int] = mapped_column(Integer, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='available', nullable=False)
    buyer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('user.id'), nullable=True)
    reserved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    bookings: Mapped[list['BookingModel']] = relationship(
        'BookingModel',
        secondary='booking_ticket_mapping',
        back_populates='tickets',
        lazy='selectin',
    )

    __table_args__ = (
        UniqueConstraint(
            'event_id', 'section', 'subsection', 'row_number', 'seat_number', name='uq_ticket_seat'
        ),
    )
