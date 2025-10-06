from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.driven_adapter.model.booking_model import (
    BookingModel,
    BookingTicketModel,
)


if TYPE_CHECKING:
    pass


class IBookingCommandRepoImpl(IBookingCommandRepo):
    """
    Booking Command Repository - Data Access Layer

    Architecture Rule: Repository NEVER commits!
    - Use case is responsible for transaction management (commit/rollback)
    - Repository only performs CRUD operations (add, update, flush)
    """

    def __init__(self):
        self.session: AsyncSession  # Will be injected by use case

    @staticmethod
    def _to_entity(db_booking: BookingModel) -> Booking:
        ticket_ids = []
        if hasattr(db_booking, '__dict__') and 'tickets' in db_booking.__dict__:
            ticket_ids = [ticket.id for ticket in db_booking.tickets] if db_booking.tickets else []

        return Booking(
            buyer_id=db_booking.buyer_id,
            event_id=db_booking.event_id,
            section=db_booking.section,
            subsection=db_booking.subsection,
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
            subsection=booking.subsection,
            quantity=booking.quantity,
            total_price=booking.total_price,
            seat_selection_mode=booking.seat_selection_mode,
            seat_positions=booking.seat_positions,
            status=booking.status.value,
        )
        self.session.add(db_booking)
        await self.session.flush()
        await self.session.refresh(db_booking)
        return self._to_entity(db_booking)

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)

    @Logger.io
    async def link_tickets_to_booking(self, *, booking_id: int, ticket_ids: list[int]) -> None:
        """
        Write booking-ticket associations to booking_ticket table

        Args:
            booking_id: Booking ID
            ticket_ids: List of ticket IDs to link
        """

        # Insert all associations in one batch
        for ticket_id in ticket_ids:
            booking_ticket = BookingTicketModel(booking_id=booking_id, ticket_id=ticket_id)
            self.session.add(booking_ticket)

        await self.session.flush()

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

        # NO commit - use case handles this!
        return self._to_entity(db_booking)
