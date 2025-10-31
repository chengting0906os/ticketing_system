import asyncio
from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from opentelemetry import trace
from uuid_v7.base import uuid7

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
    4. Save minimal booking record to PostgreSQL (status=PENDING_RESERVATION)
    5. Publish event to Kafka (with section-subsection partition key)
    6. Return booking_id immediately to frontend (can start SSE subscription)

    Dependencies:
    - booking_metadata_handler: For Kvrocks metadata operations
    - booking_command_repo: For persisting booking to PostgreSQL
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
    ):
        self.booking_metadata_handler = booking_metadata_handler
        self.booking_command_repo = booking_command_repo
        self.event_publisher = event_publisher
        self.seat_availability_handler = seat_availability_handler
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
    ):
        return cls(
            booking_metadata_handler=booking_metadata_handler,
            booking_command_repo=booking_command_repo,
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
        Create booking with optimized flow - Kvrocks + PostgreSQL + Kafka

        Flow:
        1. Generate UUID7 as booking_id
        2. Validate seat availability (Fail Fast)
        3. Save booking metadata to Kvrocks (temporary, for Seat Reservation Service)
        4. Save booking to PostgreSQL (status=PENDING_RESERVATION)
        5. Publish BookingCreated event to Kafka
        6. Return booking with UUID7 id

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
            DomainError: If seat availability check fails or creation fails
        """
        with self.tracer.start_as_current_span('use_case.create_booking'):
            # Step 1: Generate UUID7 booking ID
            booking_id_uuid = uuid7()
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

            # Step 4: Create and persist booking to PostgreSQL
            # Note: Using domain entity's create method with UUID7
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

            try:
                created_booking = await self.booking_command_repo.create(booking=booking)
                Logger.base.info(
                    f'✅ [CREATE-BOOKING] Saved booking {booking_id_str} to PostgreSQL'
                )

            except Exception as e:
                Logger.base.error(f'❌ [CREATE-BOOKING] Failed to save to PostgreSQL: {e}')
                # Cleanup Kvrocks metadata on DB failure
                try:
                    await self.booking_metadata_handler.delete_booking_metadata(
                        booking_id=booking_id_str
                    )
                except Exception:
                    pass  # Best effort cleanup
                raise DomainError(f'Failed to create booking: {e}', 500)

            # Step 5: Publish domain event to Kafka
            # Fire-and-forget: Don't block response waiting for event publishing
            # The event will use section-subsection as partition key for ordering
            booking_created_event = BookingCreatedDomainEvent.from_booking(created_booking)

            asyncio.create_task(
                self.event_publisher.publish_booking_created(event=booking_created_event)
            )

            Logger.base.info(
                f'🚀 [CREATE-BOOKING] Published BookingCreated event for {booking_id_str}'
            )

            return created_booking
