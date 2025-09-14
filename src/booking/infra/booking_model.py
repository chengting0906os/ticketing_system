from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.shared.config.db_setting import Base


class BookingModel(Base):
    __tablename__ = 'booking'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'))
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'))
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey('event.id'))
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending_payment', nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    #
    buyer = relationship('User', foreign_keys=[buyer_id], lazy='select')
    seller = relationship('User', foreign_keys=[seller_id], lazy='select')
    event = relationship('EventModel', lazy='select')
