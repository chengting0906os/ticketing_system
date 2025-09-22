from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import Booking, BookingStatus
from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_publisher import publish_domain_event
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_command_repo,
)


if TYPE_CHECKING:
    from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl


class CreateBookingUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
    ):
        self.session = session
        self.booking_command_repo: 'BookingCommandRepoImpl' = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(get_booking_command_repo),
    ):
        return cls(session, booking_command_repo)

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
        if seat_selection_mode == 'manual' and selected_seats:
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
            seat_selection_mode=seat_selection_mode,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        try:
            created_booking = await self.booking_command_repo.create(booking=booking)
        except Exception as e:
            raise DomainError(f'{e}', 400)

        # Commit the database transaction
        await self.session.commit()

        # Publish BookingCreated event to notify other services
        booking_created_event = {
            'event_type': 'BookingCreated',
            'aggregate_id': created_booking.id,
            'data': {
                'buyer_id': created_booking.buyer_id,
                'event_id': created_booking.event_id,
                'seat_selection_mode': created_booking.seat_selection_mode,
                'ticket_ids': created_booking.ticket_ids,
                'status': created_booking.status.value,
                'created_at': created_booking.created_at.isoformat(),
            },
        }

        await publish_domain_event(
            event=booking_created_event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_REQUEST,
            partition_key=str(created_booking.id),
        )

        return created_booking
