from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import Booking, BookingStatus
from src.booking.infra.booking_model import BookingModel
from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger


if TYPE_CHECKING:
    pass


class BookingCommandRepoImpl(BookingCommandRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_booking: BookingModel) -> Booking:
        # For new bookings, tickets relationship won't be loaded
        # Avoid accessing it to prevent greenlet_spawn errors in async context
        ticket_ids = []
        if hasattr(db_booking, '__dict__') and 'tickets' in db_booking.__dict__:
            # Only access tickets if they're already loaded in the instance
            ticket_ids = [ticket.id for ticket in db_booking.tickets] if db_booking.tickets else []

        return Booking(
            buyer_id=db_booking.buyer_id,
            event_id=db_booking.event_id,
            section=db_booking.section,
            subsection=db_booking.subsection,  # Now directly int from DB
            quantity=db_booking.quantity,
            total_price=db_booking.total_price,
            seat_selection_mode=db_booking.seat_selection_mode or 'manual',
            seat_positions=db_booking.seat_positions or [],
            status=BookingStatus(db_booking.status),
            ticket_ids=ticket_ids if hasattr(db_booking, 'tickets') and db_booking.tickets else [],
            id=db_booking.id,
            created_at=db_booking.created_at,
            updated_at=db_booking.updated_at,
            paid_at=db_booking.paid_at,
        )

    @Logger.io
    async def create(self, *, booking: Booking) -> Booking:
        db_booking = BookingModel(
            buyer_id=booking.buyer_id,
            event_id=booking.event_id,
            section=booking.section,
            subsection=booking.subsection,  # Now directly int to DB
            quantity=booking.quantity,
            total_price=booking.total_price,
            seat_positions=booking.seat_positions,  # List[str] stored as ARRAY
            status=booking.status.value,
            seat_selection_mode=booking.seat_selection_mode,
        )
        self.session.add(db_booking)
        await self.session.flush()
        await self.session.refresh(db_booking)

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def update_status_to_pending_payment(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                status=booking.status.value,
                updated_at=booking.updated_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def update_status_to_paid(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                status=booking.status.value,
                paid_at=booking.paid_at,
                updated_at=booking.updated_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                status=booking.status.value,
                updated_at=booking.updated_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def update_status_to_failed(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                status=booking.status.value,
                updated_at=booking.updated_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def update_status_to_completed(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                status=booking.status.value,
                updated_at=booking.updated_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def update_with_ticket_details(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                ticket_ids=booking.ticket_ids,
                total_price=booking.total_price,
                status=booking.status.value,
                updated_at=booking.updated_at,
            )
            .returning(BookingModel)
        )

        result = await self.session.execute(stmt)
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            raise ValueError(f'Booking with id {booking.id} not found')

        return BookingCommandRepoImpl._to_entity(db_booking)

    @Logger.io
    async def cancel_booking_atomically(self, *, booking_id: int, buyer_id: int) -> Booking:
        from sqlalchemy import select

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

        return BookingCommandRepoImpl._to_entity(db_booking)
