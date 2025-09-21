from datetime import datetime
from typing import List

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.booking.domain.booking_entity import Booking, BookingStatus
from src.booking.domain.booking_repo import BookingRepo
from src.booking.infra.booking_model import BookingModel
from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger


class BookingRepoImpl(BookingRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_booking: BookingModel) -> Booking:
        return Booking(
            buyer_id=db_booking.buyer_id,
            seller_id=db_booking.seller_id,
            event_id=db_booking.event_id,
            total_price=db_booking.price,
            status=BookingStatus(db_booking.status),
            created_at=db_booking.created_at,
            updated_at=db_booking.updated_at,
            paid_at=db_booking.paid_at,
            id=db_booking.id,
        )

    @staticmethod
    def _to_booking_dict(db_booking: BookingModel) -> dict:
        return {
            'id': db_booking.id,
            'buyer_id': db_booking.buyer_id,
            'seller_id': db_booking.seller_id,
            'event_id': db_booking.event_id,
            'price': db_booking.price,
            'status': db_booking.status,
            'created_at': db_booking.created_at,
            'paid_at': db_booking.paid_at,
            'event_name': db_booking.event.name if db_booking.event else 'Unknown Event',
            'buyer_name': db_booking.buyer.name if db_booking.buyer else 'Unknown Buyer',
            'seller_name': db_booking.seller.name if db_booking.seller else 'Unknown Seller',
        }

    @Logger.io
    async def create(self, *, booking: Booking) -> Booking:
        db_booking = BookingModel(
            buyer_id=booking.buyer_id,
            seller_id=booking.seller_id,
            event_id=booking.event_id,
            price=booking.total_price,
            status=booking.status.value,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
            paid_at=booking.paid_at,
        )
        self.session.add(db_booking)
        await self.session.flush()
        await self.session.refresh(db_booking)

        return BookingRepoImpl._to_entity(db_booking)

    @Logger.io
    async def get_by_id(self, *, booking_id: int) -> Booking | None:
        result = await self.session.execute(
            select(BookingModel).where(BookingModel.id == booking_id)
        )
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            return None

        return BookingRepoImpl._to_entity(db_booking)

    @Logger.io(truncate_content=True)
    async def get_by_event_id(self, *, event_id: int) -> Booking | None:
        result = await self.session.execute(
            select(BookingModel)
            .where(BookingModel.event_id == event_id)
            .where(BookingModel.status != BookingStatus.CANCELLED.value)
        )
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            return None

        return BookingRepoImpl._to_entity(db_booking)

    @Logger.io
    async def get_by_buyer(self, *, buyer_id: int) -> List[Booking]:
        result = await self.session.execute(
            select(BookingModel).where(BookingModel.buyer_id == buyer_id).order_by(BookingModel.id)
        )
        db_bookings = result.scalars().all()

        return [BookingRepoImpl._to_entity(db_booking) for db_booking in db_bookings]

    @Logger.io
    async def get_by_seller(self, *, seller_id: int) -> List[Booking]:
        result = await self.session.execute(
            select(BookingModel)
            .where(BookingModel.seller_id == seller_id)
            .order_by(BookingModel.id)
        )
        db_bookings = result.scalars().all()

        return [BookingRepoImpl._to_entity(db_booking) for db_booking in db_bookings]

    @Logger.io
    async def update(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                buyer_id=booking.buyer_id,
                seller_id=booking.seller_id,
                event_id=booking.event_id,
                price=booking.total_price,
                status=booking.status.value,
                updated_at=booking.updated_at,
                paid_at=booking.paid_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingRepoImpl._to_entity(db_booking)

    @Logger.io
    async def cancel_booking_atomically(self, *, booking_id: int, buyer_id: int) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking_id)
            .where(BookingModel.buyer_id == buyer_id)
            .where(BookingModel.status == BookingStatus.PENDING_PAYMENT.value)
            .values(status=BookingStatus.CANCELLED.value, updated_at=datetime.now())
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            check_stmt = select(BookingModel).where(BookingModel.id == booking_id)
            check_result = await self.session.execute(check_stmt)
            existing_booking = check_result.scalar_one_or_none()

            if not existing_booking:
                raise NotFoundError('Booking not found')
            elif existing_booking.buyer_id != buyer_id:
                raise ForbiddenError('Only the buyer can cancel this booking')
            elif existing_booking.status == BookingStatus.PAID.value:
                raise DomainError('Cannot cancel paid booking')
            elif existing_booking.status == BookingStatus.CANCELLED.value:
                raise DomainError('Booking already cancelled')
            else:
                raise DomainError('Unable to cancel booking')

        return BookingRepoImpl._to_entity(db_booking)

    @Logger.io
    async def get_buyer_bookings_with_details(self, *, buyer_id: int, status: str) -> List[dict]:
        query = (
            select(BookingModel)
            .options(
                selectinload(BookingModel.event),
                selectinload(BookingModel.buyer),
                selectinload(BookingModel.seller),
            )
            .where(BookingModel.buyer_id == buyer_id)
        )

        if status:
            query = query.where(BookingModel.status == status)

        result = await self.session.execute(query.order_by(BookingModel.id))
        db_bookings = result.scalars().all()

        return [BookingRepoImpl._to_booking_dict(db_booking) for db_booking in db_bookings]

    @Logger.io
    async def get_seller_bookings_with_details(self, *, seller_id: int, status: str) -> List[dict]:
        query = (
            select(BookingModel)
            .options(
                selectinload(BookingModel.event),
                selectinload(BookingModel.buyer),
                selectinload(BookingModel.seller),
            )
            .where(BookingModel.seller_id == seller_id)
        )

        if status:
            query = query.where(BookingModel.status == status)

        result = await self.session.execute(query.order_by(BookingModel.id))
        db_bookings = result.scalars().all()

        return [BookingRepoImpl._to_booking_dict(db_booking) for db_booking in db_bookings]
