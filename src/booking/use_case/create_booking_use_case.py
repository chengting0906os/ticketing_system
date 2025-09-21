from typing import List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_aggregate import BookingAggregate
from src.booking.domain.booking_entity import Booking, BookingStatus
from src.booking.domain.booking_repo import BookingRepo
from src.event_ticketing.domain.event_repo import EventRepo
from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.config.db_setting import get_async_session
from src.shared.event_bus.ticket_event_publisher import publish_booking_created_by_subsections
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_repo,
    get_event_repo,
    get_ticket_repo,
    get_user_repo,
)
from src.user.domain.user_repo import UserRepo


class CreateBookingUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_repo: BookingRepo,
        user_repo: UserRepo,
        ticket_repo: TicketRepo,
        event_repo: EventRepo,
    ):
        self.session = session
        self.booking_repo = booking_repo
        self.user_repo = user_repo
        self.ticket_repo = ticket_repo
        self.event_repo = event_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_repo: BookingRepo = Depends(get_booking_repo),
        user_repo: UserRepo = Depends(get_user_repo),
        ticket_repo: TicketRepo = Depends(get_ticket_repo),
        event_repo: EventRepo = Depends(get_event_repo),
    ):
        return cls(session, booking_repo, user_repo, ticket_repo, event_repo)

    @Logger.io
    async def create_booking(
        self,
        *,
        buyer_id: int,
        event_id: int,
        seat_selection_mode: str,
        selected_seats: Optional[List[dict]] = None,
        numbers_of_seats: Optional[int] = None,
    ) -> Booking:
        # Validate seat selection parameters
        if seat_selection_mode == 'manual':
            if not selected_seats or len(selected_seats) == 0:
                raise DomainError('selected_seats is required for manual selection', 400)
            if numbers_of_seats is not None:
                raise DomainError('Cannot specify numbers_of_seats for manual selection', 400)
            if len(selected_seats) > 4:
                raise DomainError('Maximum 4 tickets per booking', 400)
        elif seat_selection_mode == 'best_available':
            if selected_seats and len(selected_seats) > 0:
                raise DomainError('selected_seats must be empty for best_available selection', 400)
            if numbers_of_seats is None:
                raise DomainError('numbers_of_seats is required for best_available selection', 400)
            if numbers_of_seats < 1 or numbers_of_seats > 4:
                raise DomainError('numbers_of_seats must be between 1 and 4', 400)
        else:
            raise DomainError(
                'seat_selection_mode must be either "manual" or "best_available"', 400
            )

        buyer = await self.user_repo.get_by_id(user_id=buyer_id)
        if not buyer:
            raise DomainError('Buyer not found', 404)

        # Extract ticket IDs based on seat selection mode
        if seat_selection_mode == 'manual':
            # Extract ticket IDs from the selected_seats dict format
            ticket_ids = []
            for seat_dict in selected_seats:  # type: ignore
                # Each dict should have format {ticket_id: seat_location}
                if not isinstance(seat_dict, dict) or len(seat_dict) != 1:
                    raise DomainError('Invalid selected_seats format', 400)

                ticket_id, _ = next(iter(seat_dict.items()))  # seat_location not used here
                ticket_ids.append(ticket_id)

        elif seat_selection_mode == 'best_available':
            # Find best available consecutive seats for the specified event
            available_tickets = await self.ticket_repo.get_available_tickets_for_event(
                event_id=event_id, limit=numbers_of_seats
            )
            if len(available_tickets) < numbers_of_seats:  # type: ignore
                raise DomainError(
                    f'Not enough available seats. Requested: {numbers_of_seats}, Available: {len(available_tickets)}',
                    400,
                )
            ticket_ids = [ticket.id for ticket in available_tickets[:numbers_of_seats]]  # type: ignore

        event, seller = await self.event_repo.get_by_id_with_seller(event_id=event_id)
        if not event:
            raise DomainError('Event not found', 404)
        if not seller:
            raise DomainError('Seller not found', 404)

        # Validate event is available for booking
        if not event.is_active:
            raise DomainError('Event not active', 400)

        # Calculate total price based on event price (simplified - all tickets same price)
        # In a real system, this would come from the event or a pricing service
        total_price = len(ticket_ids) * 1000  # type: ignore

        # Create the booking entity directly with PROCESSING status
        from datetime import datetime

        booking = Booking(
            buyer_id=buyer_id,
            seller_id=seller.id,  # type: ignore
            event_id=event_id,
            total_price=total_price,
            status=BookingStatus.PROCESSING,  # Start with PROCESSING, will be updated by Kafka
            ticket_ids=ticket_ids,  # type: ignore
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        created_booking = await self.booking_repo.create(booking=booking)

        # Create aggregate for event publishing
        from src.booking.domain.value_objects import BuyerInfo, SellerInfo

        buyer_info = BuyerInfo.from_user(buyer)
        seller_info = SellerInfo.from_user(seller)

        # Create minimal aggregate just for event publishing
        aggregate = BookingAggregate(
            booking=created_booking,
            ticket_snapshots=[],  # We don't have ticket details anymore
            buyer_info=buyer_info,
            seller_info=seller_info,
        )

        # Emit domain events now that we have a booking ID
        aggregate.emit_booking_created_event()

        # Commit the database transaction
        await self.session.commit()

        # Publish domain events after successful commit using section-based partitioning
        # This will trigger event_ticketing service to reserve tickets
        try:
            await publish_booking_created_by_subsections(booking_aggregate=aggregate)
        except Exception as e:
            # Log error but don't fail the booking - events can be retried
            Logger.base.error(f'Failed to publish booking events: {e}')

        # Clear events after publishing
        aggregate.clear_events()

        return created_booking

    @Logger.io
    async def update_booking_status(self, booking: Booking) -> Booking:
        """Update an existing booking's status in the repository"""
        updated_booking = await self.booking_repo.update(booking=booking)
        await self.session.commit()
        return updated_booking
