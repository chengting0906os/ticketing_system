from typing import List, Optional
from uuid import UUID

from anyio.abc import TaskGroup
from opentelemetry import trace

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
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
    - background_task_group: Optional TaskGroup for fire-and-forget event publishing
    """

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_publisher: IBookingEventPublisher,
        seat_availability_handler: ISeatAvailabilityQueryHandler,
        background_task_group: Optional[TaskGroup] = None,
    ):
        self.booking_command_repo = booking_command_repo
        self.event_publisher = event_publisher
        self.seat_availability_handler = seat_availability_handler
        self.background_task_group = background_task_group
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def create_booking(
        self,
        *,
        buyer_id: UUID,
        event_id: UUID,
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
        with self.tracer.start_as_current_span(
            'use_case.create_booking',
            attributes={
                'buyer_id': str(buyer_id),
                'event_id': str(event_id),
                'section': section,
                'subsection': subsection,
                'seat_selection_mode': seat_selection_mode,
                'quantity': quantity,
            },
        ):
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

            with self.tracer.start_as_current_span('booking.create_entity'):
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
                with self.tracer.start_as_current_span('booking.persist_to_db'):
                    created_booking = await self.booking_command_repo.create(booking=booking)

            except Exception as e:
                raise DomainError(f'Failed to create booking: {e}', 400)
            booking_created_event = await BookingCreatedDomainEvent.from_booking(created_booking)

            # # Fire-and-forget: Use background TaskGroup if available, otherwise await synchronously
            # if self.background_task_group:
            #     publish_fn = partial(
            #         self.event_publisher.publish_booking_created, event=booking_created_event
            #     )
            #     self.background_task_group.start_soon(publish_fn)
            # else:
            await self.event_publisher.publish_booking_created(event=booking_created_event)

            return created_booking
