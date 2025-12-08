from typing import List, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from opentelemetry import trace
import uuid_utils

from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingCreatedDomainEvent
from src.service.ticketing.domain.entity.booking_entity import Booking


class CreateBookingUseCase:
    """
    Create booking use case - Direct flow (Ticketing → Reservation)

    Flow:
    1. Generate UUID7 booking_id
    2. Validate seat availability (Fail Fast)
    3. Publish event directly to Reservation Service (Kafka)
    4. Return booking_id immediately to frontend (can start SSE subscription)

    Downstream:
    - Reservation Service: Reserves seats in Kvrocks → writes to PostgreSQL → SSE broadcast

    Dependencies:
    - event_publisher: For publishing domain events to Reservation Service
    - seat_availability_handler: For checking seat availability (Fail Fast)
    """

    def __init__(
        self,
        *,
        event_publisher: IBookingEventPublisher,
        seat_availability_handler: ISeatAvailabilityQueryHandler,
    ) -> None:
        self.event_publisher = event_publisher
        self.seat_availability_handler = seat_availability_handler
        self.tracer = trace.get_tracer(__name__)

    @classmethod
    @inject
    def depends(
        cls,
        event_publisher: IBookingEventPublisher = Depends(
            Provide[Container.booking_event_publisher]
        ),
        seat_availability_handler: ISeatAvailabilityQueryHandler = Depends(
            Provide[Container.seat_availability_query_handler]
        ),
    ) -> Self:
        return cls(
            event_publisher=event_publisher,
            seat_availability_handler=seat_availability_handler,
        )

    @Logger.io
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
        Create booking - Direct flow (Ticketing → Reservation)

        Flow:
        1. Generate UUID7 as booking_id
        2. Validate seat availability (Fail Fast)
        3. Publish BookingCreated event directly to Reservation Service
        4. Return booking with UUID7 id (frontend can start SSE subscription)

        Downstream:
        - Reservation Service: reserves seats → writes to PostgreSQL → SSE broadcast

        Args:
            buyer_id: ID of the buyer
            event_id: ID of the event
            section: Section identifier (e.g., 'A', 'B')
            subsection: Subsection number
            seat_selection_mode: 'manual' or 'best_available'
            seat_positions: List of seat identifiers (for manual mode)
            quantity: Number of seats to book

        Returns:
            Created booking entity with UUID7 id

        Raises:
            DomainError: If seat availability check fails
        """
        # Step 1: Generate UUID7 booking ID
        booking_id_uuid = uuid_utils.uuid7()  # Generate UUID7
        booking_id_str = str(booking_id_uuid)

        with self.tracer.start_as_current_span(
            'use_case.create_booking',
            attributes={
                'booking.id': booking_id_str,
            },
        ):
            booking = Booking.create(
                id=booking_id_uuid,  # UUID7 object
                buyer_id=buyer_id,
                event_id=event_id,
                section=section,
                subsection=subsection,
                seat_selection_mode=seat_selection_mode,
                seat_positions=seat_positions,
                quantity=quantity,
            )

            Logger.base.info(
                f'📝 [CREATE-BOOKING] Generated UUID7: {booking_id_str} '
                f'for buyer {buyer_id}, section {section}-{subsection}'
            )

            # Step 2: Fail Fast - Check seat availability before any writes
            # Also retrieves config (rows, cols, price) to pass to downstream services
            availability_result = (
                await self.seat_availability_handler.check_subsection_availability(
                    event_id=event_id,
                    section=section,
                    subsection=subsection,
                    required_quantity=quantity,
                )
            )

            if not availability_result.has_enough_seats:
                raise DomainError(f'Insufficient seats available in section {section}-{subsection}')

            # Step 3: Publish event to Booking Service
            # Uses section-subsection as partition key for ordering
            # Includes config (rows, cols, price) to pass to downstream services
            booking_created_event = BookingCreatedDomainEvent.from_booking_with_config(
                booking, availability_result
            )

            await self.event_publisher.publish_booking_created(event=booking_created_event)
            Logger.base.info(
                f'🚀 [TICKETING→RESERVATION] Published BookingCreated event for {booking_id_str}'
            )

            # Step 4: Return booking (downstream services handle metadata + reservation + PostgreSQL)
            return booking
