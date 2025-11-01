from uuid_utils import UUID
from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator, Callable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.driven_adapter.model.booking_model import BookingModel
from src.service.ticketing.driven_adapter.model.event_model import EventModel
from src.service.ticketing.driven_adapter.model.ticket_model import TicketModel
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class BookingQueryRepoImpl(IBookingQueryRepo):
    def __init__(
        self, session_factory: Callable[..., AsyncContextManager[AsyncSession]] | None = None
    ):
        self.session_factory = session_factory
        self.session: AsyncSession | None = None

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get session for query execution.

        If session is injected (from UoW), yield it directly without context management.
        Otherwise, use session_factory context manager.
        """
        if self.session is not None:
            # Session injected by UoW - use directly (no context manager needed)
            yield self.session
        elif self.session_factory is not None:
            # Use session_factory context manager
            async with self.session_factory() as session:
                yield session
        else:
            raise RuntimeError('No session or session_factory available')

    @staticmethod
    def _to_entity(db_booking: BookingModel) -> Booking:
        """
        Convert BookingModel to Booking entity

        Note:
        - ticket_ids are managed via booking_ticket_mapping association table,
          not stored in the Booking entity itself.
        - SQLAlchemy with as_uuid=True returns stdlib uuid.UUID, but Pydantic expects string or uuid_utils.UUID.
          We convert to string to ensure compatibility.
        """
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
            id=UUID(str(db_booking.id)),  # Convert stdlib uuid.UUID to uuid_utils.UUID
            created_at=db_booking.created_at,
            updated_at=db_booking.updated_at,
            paid_at=db_booking.paid_at,
        )

    @staticmethod
    def _to_booking_dict(db_booking: BookingModel, tickets_data: list | None = None) -> dict:
        # Safely access event relationship if loaded
        event_name = 'Unknown Event'
        seller_name = 'Unknown Seller'
        venue_name = 'Unknown Venue'
        if hasattr(db_booking, '__dict__') and 'event' in db_booking.__dict__ and db_booking.event:
            event_name = db_booking.event.name  # pyright: ignore[reportAttributeAccessIssue]
            venue_name = db_booking.event.venue_name  # pyright: ignore[reportAttributeAccessIssue]
            # Get seller name from event's seller relationship
            if hasattr(db_booking.event, 'seller') and db_booking.event.seller:  # pyright: ignore[reportAttributeAccessIssue]
                seller_name = db_booking.event.seller.name  # pyright: ignore[reportAttributeAccessIssue]

        # Safely access buyer relationship if loaded
        buyer_name = 'Unknown Buyer'
        if hasattr(db_booking, '__dict__') and 'buyer' in db_booking.__dict__ and db_booking.buyer:
            buyer_name = db_booking.buyer.name  # pyright: ignore[reportAttributeAccessIssue]

        # Use tickets_data passed from caller (queried via get_tickets_by_booking_id)
        if tickets_data is None:
            tickets_data = []

        return {
            'id': str(
                db_booking.id
            ),  # Convert uuid.UUID (stdlib) to string for Pydantic validation
            'buyer_id': db_booking.buyer_id,
            'event_id': db_booking.event_id,
            'total_price': db_booking.total_price,
            'status': db_booking.status,
            'created_at': db_booking.created_at,
            'paid_at': db_booking.paid_at,
            'event_name': event_name,
            'buyer_name': buyer_name,
            'seller_name': seller_name,
            'venue_name': venue_name,
            'section': db_booking.section,
            'subsection': db_booking.subsection,
            'quantity': db_booking.quantity,
            'seat_selection_mode': db_booking.seat_selection_mode or 'manual',
            'seat_positions': db_booking.seat_positions or [],
            'tickets': tickets_data,
        }

    @Logger.io
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        async with self._get_session() as session:
            result = await session.execute(
                select(BookingModel).where(BookingModel.id == booking_id)
            )
            db_booking = result.scalar_one_or_none()

            if not db_booking:
                return None

            return BookingQueryRepoImpl._to_entity(db_booking)

    @Logger.io
    async def get_by_id_with_details(self, *, booking_id: UUID) -> dict | None:
        """Get booking by ID with full details (event, user, seller info)"""

        async with self._get_session() as session:
            result = await session.execute(
                select(BookingModel)
                .options(
                    selectinload(BookingModel.event).selectinload(EventModel.seller),  # pyright: ignore[reportAttributeAccessIssue]
                    selectinload(BookingModel.buyer),  # pyright: ignore[reportAttributeAccessIssue]
                )
                .where(BookingModel.id == booking_id)
            )
            db_booking = result.scalar_one_or_none()

            if not db_booking:
                return None

            # Query tickets using seat_positions
            tickets = await self.get_tickets_by_booking_id(booking_id=booking_id)
            tickets_data = [
                {
                    'id': ticket.id,
                    'section': ticket.section,
                    'subsection': ticket.subsection,
                    'row': ticket.row,
                    'seat': ticket.seat,
                    'price': ticket.price,
                    'status': ticket.status.value,
                }
                for ticket in tickets
            ]

            return BookingQueryRepoImpl._to_booking_dict(db_booking, tickets_data=tickets_data)

    @Logger.io
    async def get_buyer_bookings_with_details(self, *, buyer_id: int, status: str) -> List[dict]:
        from src.service.ticketing.driven_adapter.model.event_model import EventModel

        async with self._get_session() as session:
            query = (
                select(BookingModel)
                .options(
                    selectinload(BookingModel.event).selectinload(EventModel.seller),  # pyright: ignore[reportAttributeAccessIssue]
                    selectinload(BookingModel.buyer),  # pyright: ignore[reportAttributeAccessIssue]
                )
                .where(BookingModel.buyer_id == buyer_id)
            )

            if status:
                query = query.where(BookingModel.status == status)

            result = await session.execute(query.order_by(BookingModel.id))
            db_bookings = result.scalars().all()

            # Query tickets for each booking
            bookings_with_tickets = []
            for db_booking in db_bookings:
                tickets = await self.get_tickets_by_booking_id(booking_id=db_booking.id)
                tickets_data = [
                    {
                        'id': ticket.id,
                        'section': ticket.section,
                        'subsection': ticket.subsection,
                        'row': ticket.row,
                        'seat': ticket.seat,
                        'price': ticket.price,
                        'status': ticket.status.value,
                    }
                    for ticket in tickets
                ]
                bookings_with_tickets.append(
                    BookingQueryRepoImpl._to_booking_dict(db_booking, tickets_data=tickets_data)
                )

            return bookings_with_tickets

    @Logger.io(truncate_content=True)  # type: ignore
    async def get_seller_bookings_with_details(self, *, seller_id: int, status: str) -> List[dict]:
        from src.service.ticketing.driven_adapter.model.event_model import EventModel

        async with self._get_session() as session:
            query = (
                select(BookingModel)
                .join(EventModel, BookingModel.event_id == EventModel.id)
                .options(
                    selectinload(BookingModel.event).selectinload(EventModel.seller),  # pyright: ignore[reportAttributeAccessIssue]
                    selectinload(BookingModel.buyer),  # pyright: ignore[reportAttributeAccessIssue]
                )
                .where(EventModel.seller_id == seller_id)
            )

            if status:
                query = query.where(BookingModel.status == status)

            result = await session.execute(query.order_by(BookingModel.id))
            db_bookings = result.scalars().all()

            # Query tickets for each booking
            bookings_with_tickets = []
            for db_booking in db_bookings:
                tickets = await self.get_tickets_by_booking_id(booking_id=db_booking.id)
                tickets_data = [
                    {
                        'id': ticket.id,
                        'section': ticket.section,
                        'subsection': ticket.subsection,
                        'row': ticket.row,
                        'seat': ticket.seat,
                        'price': ticket.price,
                        'status': ticket.status.value,
                    }
                    for ticket in tickets
                ]
                bookings_with_tickets.append(
                    BookingQueryRepoImpl._to_booking_dict(db_booking, tickets_data=tickets_data)
                )

            return bookings_with_tickets

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List['TicketRef']:
        """
        Get all tickets for a booking using seat_positions

        Uses booking's event_id, section, subsection, and seat_positions to find matching tickets
        via the unique constraint (event_id, section, subsection, row_number, seat_number)
        """
        async with self._get_session() as session:
            # First get booking info
            result = await session.execute(
                select(
                    BookingModel.event_id,
                    BookingModel.section,
                    BookingModel.subsection,
                    BookingModel.seat_positions,
                ).where(BookingModel.id == booking_id)
            )
            booking_row = result.first()

            if not booking_row or not booking_row.seat_positions:
                return []

            # Build conditions to match tickets
            # seat_positions format: ["1-1", "1-2"] means row-seat pairs
            conditions = []
            for seat_pos in booking_row.seat_positions:
                try:
                    row_num, seat_num = seat_pos.split('-')
                    conditions.append(
                        (TicketModel.row_number == int(row_num))
                        & (TicketModel.seat_number == int(seat_num))
                    )
                except (ValueError, AttributeError):
                    # Skip invalid seat position format
                    continue

            if not conditions:
                return []

            # Query tickets
            from sqlalchemy import or_

            result = await session.execute(
                select(TicketModel).where(
                    TicketModel.event_id == booking_row.event_id,
                    TicketModel.section == booking_row.section,
                    TicketModel.subsection == booking_row.subsection,
                    or_(*conditions),
                )
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
