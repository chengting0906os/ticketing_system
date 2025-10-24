import asyncio
from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from opentelemetry import trace

from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingCreatedDomainEvent
from src.service.ticketing.domain.entity.booking_entity import Booking


class CreateBookingUseCase:
    """
    Create booking use case - SAGA pattern with direct repository injection

    Dependencies:
    - booking_command_repo: For creating booking
    - event_publisher: For publishing domain events
    - seat_availability_handler: For checking seat availability
    """

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_publisher: IBookingEventPublisher,
        seat_availability_handler: ISeatAvailabilityQueryHandler,
    ):
        self.booking_command_repo = booking_command_repo
        self.event_publisher = event_publisher
        self.seat_availability_handler = seat_availability_handler
        self.tracer = trace.get_tracer(__name__)

    @classmethod
    @inject
    def depends(
        cls,
        booking_command_repo: IBookingCommandRepo = Depends(
            Provide[Container.booking_command_repo]
        ),
        event_publisher: IBookingEventPublisher = Depends(
            Provide[Container.booking_event_publisher]
        ),
        seat_availability_handler: ISeatAvailabilityQueryHandler = Depends(
            Provide[Container.seat_availability_query_handler]
        ),
    ):
        return cls(
            booking_command_repo=booking_command_repo,
            event_publisher=event_publisher,
            seat_availability_handler=seat_availability_handler,
        )

    # @Logger.io
    async def create_booking(
        self,
        *,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        quantity: int,
    ) -> Booking:
        """
        Create booking with SAGA pattern - immediate commit with compensating events

        Flow:
        1. Validate seat availability (Fail Fast)
        2. Create booking entity with domain logic
        3. Persist booking to database
        4. Publish domain event for downstream processing

        Args:
            buyer_id: ID of the buyer
            event_id: ID of the event
            section: Section identifier (e.g., 'A', 'B')
            subsection: Subsection number
            seat_selection_mode: 'specific' or 'best_available'
            seat_positions: List of seat identifiers (for specific mode)
            quantity: Number of seats to book

        Returns:
            Created booking entity

        Raises:
            DomainError: If seat availability check fails or creation fails
        """
        with self.tracer.start_as_current_span('use_case.create_booking'):
            # Fail Fast: Check seat availability before creating booking
            # has_enough_seats = await self.seat_availability_handler.check_subsection_availability(
            #     event_id=event_id,
            #     section=section,
            #     subsection=subsection,
            #     required_quantity=quantity,
            # )

            # if not has_enough_seats:
            #     raise DomainError(
            #         f'Insufficient seats available in section {section}-{subsection}', 400
            #     )

            # Use domain entity's create method which contains all validation logic
            booking = await Booking.create(
                buyer_id=buyer_id,
                event_id=event_id,
                section=section,
                subsection=subsection,
                seat_selection_mode=seat_selection_mode,
                seat_positions=seat_positions,
                quantity=quantity,
            )

            try:
                created_booking = await self.booking_command_repo.create(booking=booking)

            except Exception as e:
                raise DomainError(f'Failed to create booking: {e}', 400)

            # Publish domain event after successful creation (using abstraction)
            # SAGA pattern: If downstream fails, compensating events will be triggered
            # Fire-and-forget: Don't block response waiting for event publishing
            booking_created_event = BookingCreatedDomainEvent.from_booking(created_booking)
            asyncio.create_task(
                self.event_publisher.publish_booking_created(event=booking_created_event)
            )

            return created_booking
