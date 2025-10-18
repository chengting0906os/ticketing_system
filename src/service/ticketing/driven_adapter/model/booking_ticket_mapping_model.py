from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.platform.database.db_setting import Base


class BookingTicketMappingModel(Base):
    __tablename__ = 'booking_ticket_mapping'

    booking_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
