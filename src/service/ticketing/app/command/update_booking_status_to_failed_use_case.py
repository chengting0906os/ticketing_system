from datetime import datetime, timezone
from typing import List

from opentelemetry import trace
from uuid_utils import UUID

from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToFailedUseCase:
    """
    Create booking in FAILED status (from Kafka event)

    Called when seat reservation fails - booking doesn't exist in PostgreSQL yet.
    Creates booking directly from Kafka event data (no query, no Kvrocks read).

    Dependencies:
    - booking_command_repo: For creating FAILED booking in PostgreSQL
    - event_broadcaster: For real-time SSE updates (optional)
    """

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_broadcaster: IInMemoryEventBroadcaster,
    ):
        self.booking_command_repo = booking_command_repo
        self.event_broadcaster = event_broadcaster
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def execute(
        self,
        *,
        booking_id: UUID,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        error_message: str | None = None,
    ) -> Booking | None:
        """
        Create booking in FAILED status from Kafka event data

        Args:
            booking_id: Booking ID (UUID7 from Kafka event)
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            quantity: Originally requested quantity
            seat_selection_mode: 'manual' or 'best_available'
            seat_positions: Originally requested seat positions
            error_message: Error message from seat reservation failure

        Returns:
            Created booking in FAILED status, or None if creation fails
        """
        with self.tracer.start_as_current_span(
            'use_case.update_booking_to_failed',
            attributes={
                'booking.id': str(booking_id),
                'error.message': error_message or '',
            },
        ):
            try:
                # Directly create FAILED booking (no query, booking doesn't exist yet)
                failed_booking = await self.booking_command_repo.create_failed_booking_directly(
                    booking_id=booking_id,
                    buyer_id=buyer_id,
                    event_id=event_id,
                    section=section,
                    subsection=subsection,
                    seat_selection_mode=seat_selection_mode,
                    seat_positions=seat_positions,
                    quantity=quantity,
                )

                Logger.base.info(
                    f'✅ [BOOKING-FAILED] Created booking {booking_id} in FAILED status: {error_message}'
                )

                # Broadcast SSE event for real-time updates
                try:
                    await self.event_broadcaster.broadcast(
                        booking_id=booking_id,
                        event_data={
                            'event_type': 'status_update',
                            'booking_id': str(booking_id),
                            'status': 'failed',
                            'error_message': error_message,
                            'updated_at': datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    Logger.base.debug(
                        f'📡 [SSE] Broadcasted failed status for booking {booking_id}'
                    )
                except Exception as e:
                    # Don't fail use case if broadcast fails
                    Logger.base.warning(f'⚠️ [SSE] Failed to broadcast event: {e}')

                return failed_booking

            except Exception as e:
                Logger.base.error(
                    f'❌ [BOOKING-FAILED] Failed to create FAILED booking {booking_id}: {e}'
                )
                return None
