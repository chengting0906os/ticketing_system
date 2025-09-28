from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.booking.domain.booking_entity import Booking, BookingStatus
from src.booking.domain.booking_query_repo import BookingQueryRepo
from src.booking.infra.booking_model import BookingModel
from src.event_ticketing.infra.ticket_model import TicketModel
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.domain.enum.ticket_status import TicketStatus
from src.shared_kernel.domain.value_object.ticket_ref import TicketRef


class BookingQueryRepoImpl(BookingQueryRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_booking: BookingModel) -> Booking:
        # Safely handle tickets relationship to avoid greenlet_spawn errors
        ticket_ids = []
        if hasattr(db_booking, '__dict__') and 'tickets' in db_booking.__dict__:
            # Only access tickets if they're already loaded in the instance
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
            ticket_ids=ticket_ids,
            id=db_booking.id,
            created_at=db_booking.created_at,
            updated_at=db_booking.updated_at,
            paid_at=db_booking.paid_at,
        )

    @staticmethod
    def _to_booking_dict(db_booking: BookingModel) -> dict:
        # Safely access event relationship if loaded
        event_name = 'Unknown Event'
        seller_name = 'Unknown Seller'
        if hasattr(db_booking, '__dict__') and 'event' in db_booking.__dict__ and db_booking.event:
            event_name = db_booking.event.name  # pyright: ignore[reportAttributeAccessIssue]
            if hasattr(db_booking.event, 'seller_id'):
                seller_name = f'Seller {db_booking.event.seller_id}'

        # Safely access buyer relationship if loaded
        buyer_name = 'Unknown Buyer'
        if hasattr(db_booking, '__dict__') and 'buyer' in db_booking.__dict__ and db_booking.buyer:
            buyer_name = db_booking.buyer.name  # pyright: ignore[reportAttributeAccessIssue]

        return {
            'id': db_booking.id,
            'buyer_id': db_booking.buyer_id,
            'event_id': db_booking.event_id,
            'total_price': db_booking.total_price,
            'status': db_booking.status,
            'created_at': db_booking.created_at,
            'paid_at': db_booking.paid_at,
            'event_name': event_name,
            'buyer_name': buyer_name,
            'seller_name': seller_name,
        }

    @Logger.io
    async def get_by_id(self, *, booking_id: int) -> Booking | None:
        result = await self.session.execute(
            select(BookingModel).where(BookingModel.id == booking_id)
        )
        db_booking = result.scalar_one_or_none()

        if not db_booking:
            return None

        return BookingQueryRepoImpl._to_entity(db_booking)

    @Logger.io(truncate_content=True)
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

        return [BookingQueryRepoImpl._to_booking_dict(db_booking) for db_booking in db_bookings]

    @Logger.io(truncate_content=True)
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

        return [BookingQueryRepoImpl._to_booking_dict(db_booking) for db_booking in db_bookings]

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List['TicketRef']:
        """Get all tickets for a booking using the ticket_ids stored in the booking"""

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
            ticket = TicketRef(
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
