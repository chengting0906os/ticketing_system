from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.platform.database.db_setting import Base


class SubsectionStatModel(Base):
    """Subsection-level statistics for seat availability tracking.

    Stores aggregated counts (available, reserved, sold) per subsection.
    Updated by PostgreSQL trigger when ticket status changes.
    """

    __tablename__ = 'subsection_stats'

    # Composite primary key
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('event.id', ondelete='CASCADE'), primary_key=True
    )
    section: Mapped[str] = mapped_column(String(10), primary_key=True)
    subsection: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Stats fields
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[int] = mapped_column(Integer, server_default='0', nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, server_default='0', nullable=False)
    sold: Mapped[int] = mapped_column(Integer, server_default='0', nullable=False)
    updated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
