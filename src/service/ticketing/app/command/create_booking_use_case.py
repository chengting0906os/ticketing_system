from typing import List

import anyio.abc
from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from opentelemetry import trace
import uuid_utils

from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingCreatedDomainEvent
from src.service.ticketing.domain.entity.booking_entity import Booking


class CreateBookingUseCase:
    """
    Create booking use case - Optimized flow with Kvrocks metadata

    New Flow (Optimized):
    1. Generate UUID7 booking_id
    2. Validate seat availability (Fail Fast)
    3. Save booking metadata to Kvrocks (fast, temporary storage)
    4. Publish event to Kafka (with section-subsection partition key)
    5. Return booking_id immediately to frontend (can start SSE subscription)
    6. Seat Reservation Service consumes event → reserves seats in Kvrocks → publishes SeatsReserved
    7. Ticketing Service consumes SeatsReserved → upserts booking to PostgreSQL

    Dependencies:
    - booking_metadata_handler: For Kvrocks metadata operations
    - event_publisher: For publishing domain events
    - seat_availability_handler: For checking seat availability
    """

    def __init__(
        self,
        *,
        booking_metadata_handler: IBookingMetadataHandler,
        booking_command_repo: IBookingCommandRepo,
        event_publisher: IBookingEventPublisher,
        seat_availability_handler: ISeatAvailabilityQueryHandler,
        task_group: anyio.abc.TaskGroup,
    ):
        self.booking_metadata_handler = booking_metadata_handler
        self.booking_command_repo = booking_command_repo
        self.event_publisher = event_publisher
        self.seat_availability_handler = seat_availability_handler
        self.task_group = task_group
        self.tracer = trace.get_tracer(__name__)

    @classmethod
    @inject
    def depends(
        cls,
        booking_metadata_handler: IBookingMetadataHandler = Depends(
            Provide[Container.booking_metadata_handler]
        ),
        booking_command_repo: IBookingCommandRepo = Depends(
            Provide[Container.booking_command_repo]
        ),
        event_publisher: IBookingEventPublisher = Depends(
            Provide[Container.booking_event_publisher]
        ),
        seat_availability_handler: ISeatAvailabilityQueryHandler = Depends(
            Provide[Container.seat_availability_query_handler]
        ),
        task_group: anyio.abc.TaskGroup = Depends(Provide[Container.task_group]),
    ):
        return cls(
            booking_metadata_handler=booking_metadata_handler,
            booking_command_repo=booking_command_repo,
            event_publisher=event_publisher,
            seat_availability_handler=seat_availability_handler,
            task_group=task_group,
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
        Create booking with optimized flow - Kvrocks + Kafka (PostgreSQL upsert by Reservation Service)

        Flow:
        1. Generate UUID7 as booking_id
        2. Validate seat availability (Fail Fast)
        3. Save booking metadata to Kvrocks (temporary, for Seat Reservation Service)
        4. Publish BookingCreated event to Kafka
        5. Return booking with UUID7 id (PostgreSQL insertion happens later via event consumer)

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
            DomainError: If seat availability check fails or metadata save fails
        """
        with self.tracer.start_as_current_span('use_case.create_booking'):
            # Step 1: Generate UUID7 booking ID
            booking_id_uuid = uuid_utils.uuid7()  # Generate UUID7
            booking_id_str = str(booking_id_uuid)

            Logger.base.info(
                f'📝 [CREATE-BOOKING] Generated UUID7: {booking_id_str} '
                f'for buyer {buyer_id}, section {section}-{subsection}'
            )

            # Step 2: Fail Fast - Check seat availability before any writes
            has_enough_seats = await self.seat_availability_handler.check_subsection_availability(
                event_id=event_id,
                section=section,
                subsection=subsection,
                required_quantity=quantity,
            )

            if not has_enough_seats:
                raise DomainError(
                    f'Insufficient seats available in section {section}-{subsection}', 400
                )

            # Step 3: Save booking metadata to Kvrocks (fast, temporary storage)
            # This will be used by Seat Reservation Service during processing
            try:
                await self.booking_metadata_handler.save_booking_metadata(
                    booking_id=booking_id_str,
                    buyer_id=buyer_id,
                    event_id=event_id,
                    section=section,
                    subsection=subsection,
                    quantity=quantity,
                    seat_selection_mode=seat_selection_mode,
                    seat_positions=seat_positions,
                )
            except Exception as e:
                Logger.base.error(f'❌ [CREATE-BOOKING] Failed to save Kvrocks metadata: {e}')
                raise DomainError(f'Failed to save booking metadata: {e}', 500)

            # Step 4: Create booking entity (for event publishing)
            # Note: Booking will be created by Seat Reservation Service after successful reservation
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

            # Step 5: Publish domain event to Kafka (fire-and-forget)
            # Use task_group for non-blocking event publishing
            # The event will use section-subsection as partition key for ordering
            booking_created_event = BookingCreatedDomainEvent.from_booking(booking)

            # Wrapper function for fire-and-forget event publishing
            async def _publish_event() -> None:
                await self.event_publisher.publish_booking_created(event=booking_created_event)

            self.task_group.start_soon(_publish_event)  # type: ignore[arg-type]
            Logger.base.info(
                f'🚀 [CREATE-BOOKING] Scheduled BookingCreated event for {booking_id_str}'
            )

            return booking
