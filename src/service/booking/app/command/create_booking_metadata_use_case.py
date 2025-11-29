"""
Create Booking Metadata Use Case

Booking Service use case that:
1. Receives booking request from Ticketing Service
2. Saves booking metadata to Kvrocks
3. Publishes ReservationRequestEvent to Reservation Service

Design Principle: No decision logic - receive and forward.
"""

from typing import List, Optional

from opentelemetry import trace

from src.platform.logging.loguru_io import Logger
from src.service.booking.app.interface.i_booking_reservation_event_publisher import (
    IBookingReservationEventPublisher,
)
from src.service.booking.domain.domain_event.reservation_request_event import (
    ReservationRequestEvent,
)
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)
from src.service.shared_kernel.domain.value_object import SubsectionConfig


class CreateBookingMetadataUseCase:
    """
    Booking Service Use Case - Creates booking metadata and forwards to Reservation.

    Responsibilities:
    1. Receive booking request from Ticketing Service (via Kafka)
    2. Save booking metadata to Kvrocks (with TTL)
    3. Publish ReservationRequestEvent to Reservation Service

    Design Principles:
    - No decision logic: Ticketing already checked availability
    - Single Responsibility: Only manages booking metadata lifecycle
    - Event-Driven: Forwards to Reservation via Kafka
    """

    def __init__(
        self,
        *,
        booking_metadata_handler: IBookingMetadataHandler,
        event_publisher: IBookingReservationEventPublisher,
    ) -> None:
        self.booking_metadata_handler = booking_metadata_handler
        self.event_publisher = event_publisher
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def execute(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        config: Optional[SubsectionConfig] = None,
    ) -> None:
        """
        Execute booking metadata creation and forward to Reservation.

        Args:
            booking_id: UUID7 booking identifier (from Ticketing)
            buyer_id: Buyer user ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            quantity: Number of seats to reserve
            seat_selection_mode: 'manual' or 'best_available'
            seat_positions: List of seat positions (for manual mode)
            config: Optional subsection config (rows, cols, price)

        Raises:
            Exception: If save or publish fails
        """
        with self.tracer.start_as_current_span(
            'use_case.create_booking_metadata',
            attributes={
                'booking.id': booking_id,
                'booking.event_id': event_id,
                'booking.section': section,
                'booking.subsection': subsection,
                'booking.quantity': quantity,
                'booking.seat_selection_mode': seat_selection_mode,
            },
        ):
            Logger.base.info(
                f'📝 [BOOKING] Creating metadata for booking {booking_id} '
                f'(event={event_id}, section={section}-{subsection}, qty={quantity})'
            )

            # Step 1: Save booking metadata to Kvrocks
            await self.booking_metadata_handler.save_booking_metadata(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                seat_selection_mode=seat_selection_mode,
                seat_positions=seat_positions,
            )

            Logger.base.info(f'✅ [BOOKING] Saved metadata to Kvrocks: {booking_id}')

            # Step 2: Publish ReservationRequestEvent to Reservation Service
            event = ReservationRequestEvent.create(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                seat_selection_mode=seat_selection_mode,
                seat_positions=seat_positions,
                config=config,
            )

            await self.event_publisher.publish_reservation_request(event=event)

            Logger.base.info(
                f'📤 [BOOKING] Published ReservationRequestEvent to Reservation Service: {booking_id}'
            )
