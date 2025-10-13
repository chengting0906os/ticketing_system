from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.platform.database.db_setting import Base


class BookingTicketMappingModel(Base):
    __tablename__ = 'booking_ticket_mapping'

    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey('booking.id'), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey('ticket.id'), primary_key=True)
