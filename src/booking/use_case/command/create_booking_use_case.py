from datetime import datetime
from typing import List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_entity import Booking, BookingStatus
from src.booking.domain.booking_repo import BookingRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_repo,
)


class CreateBookingUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_repo: BookingRepo,
    ):
        self.session = session
        self.booking_repo = booking_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_repo: BookingRepo = Depends(get_booking_repo),
    ):
        return cls(session, booking_repo)

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

        # Extract ticket IDs based on seat selection mode
        ticket_ids = []
        if seat_selection_mode == 'manual':
            # Extract ticket IDs from the selected_seats dict format
            for seat_dict in selected_seats:  # type: ignore
                # Each dict should have format {ticket_id: seat_location}
                if not isinstance(seat_dict, dict) or len(seat_dict) != 1:
                    raise DomainError('Invalid selected_seats format', 400)

                ticket_id, _ = next(iter(seat_dict.items()))  # seat_location not used here
                ticket_ids.append(ticket_id)

        elif seat_selection_mode == 'best_available':
            # For best_available, ticket_ids will be determined by event_ticketing service
            # We create booking with empty ticket_ids, they will be populated later
            ticket_ids = []

        # For manual mode, validate that tickets are selected
        if seat_selection_mode == 'manual' and not ticket_ids:
            raise DomainError('No tickets selected for booking', 400)

        booking = Booking(
            buyer_id=buyer_id,
            event_id=event_id,
            total_price=0,  # Will be updated by event_ticketing service response later
            status=BookingStatus.PROCESSING,  # Start with PROCESSING, will be updated by Kafka
            ticket_ids=ticket_ids,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        try:
            created_booking = await self.booking_repo.create(booking=booking)
        except Exception as e:
            # Handle database constraint violations
            error_msg = str(e).lower()
            if 'buyer_id' in error_msg:
                raise DomainError('Buyer not found', 404)
            elif 'seller_id' in error_msg:
                raise DomainError('Seller not found', 404)
            elif 'event_id' in error_msg or 'event' in error_msg:
                raise DomainError('Event not found', 404)
            elif 'check_seller_event_consistency' in error_msg:
                raise DomainError('Invalid seller for this event', 400)
            raise

        # Commit the database transaction
        await self.session.commit()

        # TODO: Add event publishing mechanism when needed

        return created_booking

    @Logger.io
    async def update_booking_status(self, booking: Booking) -> Booking:
        """Update an existing booking's status in the repository"""
        updated_booking = await self.booking_repo.update(booking=booking)
        await self.session.commit()
        return updated_booking
