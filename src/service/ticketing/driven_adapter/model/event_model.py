from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.platform.database.db_setting import Base

if TYPE_CHECKING:
    from src.service.ticketing.driven_adapter.model.user_model import UserModel


class EventModel(Base):
    __tablename__ = 'event'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='available', nullable=False)
    venue_name: Mapped[str] = mapped_column(String(255), nullable=False)
    seating_config: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Relationships
    seller: Mapped['UserModel'] = relationship(
        'UserModel', foreign_keys=[seller_id], lazy='selectin'
    )
