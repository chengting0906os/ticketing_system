from datetime import datetime, timezone
from uuid import UUID

from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_sse_broadcaster import ISSEBroadcaster
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
)
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToCancelledUseCase:
    """
    Update booking status to CANCELLED

    Dependencies:
    - booking_command_repo: For reading and updating booking
    - event_ticketing_query_repo: For querying ticket details (seat positions)
    """

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_ticketing_query_repo: IEventTicketingQueryRepo,
        sse_broadcaster: ISSEBroadcaster,
    ):
        self.booking_command_repo = booking_command_repo
        self.event_ticketing_query_repo = event_ticketing_query_repo
        self.sse_broadcaster = sse_broadcaster

    @Logger.io
    async def execute(self, *, booking_id: UUID, buyer_id: UUID) -> Booking:
        """
        Execute the booking cancellation workflow.

        Args:
            booking_id: Booking identifier.
            buyer_id: Buyer identifier.

        Returns:
            Booking after cancellation.

        Raises:
            NotFoundError: Booking does not exist.
            ForbiddenError: Buyer is not authorized to cancel this booking.
            DomainError: Booking state does not allow cancellation (raised by domain layer).
        """
        # Fetch booking (fail fast).
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Verify ownership (fail fast).
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        # Mark as cancelled (domain validates state transition).
        cancelled_booking = await booking.cancel()
        updated_booking = await self.booking_command_repo.update_status_to_cancelled(
            booking=cancelled_booking
        )

        # Query related tickets (via seat_positions).
        tickets = await self.booking_command_repo.get_tickets_by_booking_id(booking_id=booking_id)
        ticket_ids = [ticket.id for ticket in tickets if ticket.id]

        # Build full seat identifiers from tickets.
        # Format: section-subsection-row-seat (e.g., "A-1-1-1")
        seat_positions = [
            f'{ticket.section}-{ticket.subsection}-{ticket.row}-{ticket.seat}' for ticket in tickets
        ]
        Logger.base.info(
            f'🎫 [CANCEL] Found {len(seat_positions)} seat positions: {seat_positions}'
        )

        # Publish BookingCancelledEvent to Kafka (release Kvrocks seats).
        if ticket_ids:
            Logger.base.info(
                f'🔓 [CANCEL] Publishing cancellation event for {len(ticket_ids)} tickets'
            )

            cancelled_event = BookingCancelledEvent(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=booking.event_id,
                ticket_ids=ticket_ids,
                seat_positions=seat_positions,
                cancelled_at=datetime.now(timezone.utc),
            )

            topic_name = KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                event_id=booking.event_id
            )
            partition_key = f'event-{booking.event_id}'

            await publish_domain_event(
                event=cancelled_event, topic=topic_name, partition_key=partition_key
            )

            Logger.base.info(f'✅ [CANCEL] Published BookingCancelledEvent to {topic_name}')

        # Broadcast to SSE (event-driven notification).
        await self.sse_broadcaster.broadcast(
            booking_id=booking_id,
            status_update={
                'event_type': 'booking_cancelled',
                'status': 'CANCELLED',
                'details': {
                    'cancelled_at': datetime.now(timezone.utc).isoformat(),
                    'seat_positions': seat_positions,
                },
            },
        )
        Logger.base.info(f'📤 [SSE] Broadcasted booking_cancelled to booking {booking_id}')

        Logger.base.info(f'🎯 [CANCEL] Booking {booking_id} cancelled successfully')
        return updated_booking
