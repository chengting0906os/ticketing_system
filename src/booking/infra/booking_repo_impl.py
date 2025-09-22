from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import select, update as sql_update


if TYPE_CHECKING:
    from src.event_ticketing.domain.ticket_entity import Ticket
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
            event_id=db_booking.event_id,
            total_price=db_booking.total_price,
            status=BookingStatus(db_booking.status),
            created_at=db_booking.created_at,
            updated_at=db_booking.updated_at,
            paid_at=db_booking.paid_at,
            ticket_ids=db_booking.ticket_ids or [],
            id=db_booking.id,
        )

    @staticmethod
    def _to_booking_dict(db_booking: BookingModel) -> dict:
        # Get seller information through event relationship
        seller_name = 'Unknown Seller'
        if db_booking.event and hasattr(db_booking.event, 'seller_id'):
            # In real implementation, would need to join with User table
            seller_name = f'Seller {db_booking.event.seller_id}'

        return {
            'id': db_booking.id,
            'buyer_id': db_booking.buyer_id,
            'event_id': db_booking.event_id,
            'total_price': db_booking.total_price,
            'status': db_booking.status,
            'created_at': db_booking.created_at,
            'paid_at': db_booking.paid_at,
            'event_name': db_booking.event.name if db_booking.event else 'Unknown Event',  # pyright: ignore[reportAttributeAccessIssue]
            'buyer_name': db_booking.buyer.name if db_booking.buyer else 'Unknown Buyer',  # pyright: ignore[reportAttributeAccessIssue]
            'seller_name': seller_name,
        }

    @Logger.io
    async def create(self, *, booking: Booking) -> Booking:
        db_booking = BookingModel(
            buyer_id=booking.buyer_id,
            event_id=booking.event_id,
            total_price=booking.total_price,
            status=booking.status.value,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
            paid_at=booking.paid_at,
            ticket_ids=booking.ticket_ids,
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

    @Logger.io
    async def update(self, *, booking: Booking) -> Booking:
        stmt = (
            sql_update(BookingModel)
            .where(BookingModel.id == booking.id)
            .values(
                buyer_id=booking.buyer_id,
                event_id=booking.event_id,
                total_price=booking.total_price,
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
                selectinload(BookingModel.event),  # pyright: ignore[reportAttributeAccessIssue]
                selectinload(BookingModel.buyer),  # pyright: ignore[reportAttributeAccessIssue]
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
        # Join with event table to get bookings for events owned by seller
        from src.event_ticketing.infra.event_model import EventModel

        query = (
            select(BookingModel)
            .join(EventModel, BookingModel.event_id == EventModel.id)
            .options(
                selectinload(BookingModel.event),  # pyright: ignore[reportAttributeAccessIssue]
                selectinload(BookingModel.buyer),  # pyright: ignore[reportAttributeAccessIssue]
            )
            .where(EventModel.seller_id == seller_id)
        )

        if status:
            query = query.where(BookingModel.status == status)

        result = await self.session.execute(query.order_by(BookingModel.id))
        db_bookings = result.scalars().all()

        return [BookingRepoImpl._to_booking_dict(db_booking) for db_booking in db_bookings]

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List['Ticket']:
        """Get all tickets for a booking using the ticket_ids stored in the booking"""
        from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
        from src.event_ticketing.infra.ticket_model import TicketModel

        # First get the booking to get the ticket_ids
        booking = await self.get_by_id(booking_id=booking_id)
        if not booking or not booking.ticket_ids:
            return []

        # Then get the tickets by their IDs
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.id.in_(booking.ticket_ids))
        )
        db_tickets = result.scalars().all()

        # Convert to Ticket entities
        tickets = []
        for db_ticket in db_tickets:
            ticket = Ticket(
                event_id=db_ticket.event_id,
                section=db_ticket.section,
                subsection=db_ticket.subsection,
                row=db_ticket.row_number,
                seat=db_ticket.seat_number,
                price=db_ticket.price,
                status=TicketStatus(db_ticket.status),
                buyer_id=db_ticket.buyer_id,
                id=db_ticket.id,
                created_at=db_ticket.created_at,
                updated_at=db_ticket.updated_at,
                reserved_at=db_ticket.reserved_at,
            )
            tickets.append(ticket)

        return tickets
