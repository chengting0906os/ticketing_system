from datetime import datetime, timezone
from typing import Self

from dependency_injector.wiring import Provide, inject
from uuid_utils import UUID
from fastapi import Depends

from src.platform.config.core_setting import settings
from src.platform.config.di import Container
from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
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
    ) -> None:
        self.booking_command_repo = booking_command_repo
        self.event_ticketing_query_repo = event_ticketing_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        booking_command_repo: IBookingCommandRepo = Depends(
            Provide[Container.booking_command_repo]
        ),
        event_ticketing_query_repo: IEventTicketingQueryRepo = Depends(
            Provide[Container.event_ticketing_query_repo]
        ),
    ) -> Self:
        """For FastAPI endpoint compatibility"""
        return cls(
            booking_command_repo=booking_command_repo,
            event_ticketing_query_repo=event_ticketing_query_repo,
        )

    @Logger.io
    async def execute(self, *, booking_id: UUID, buyer_id: int) -> Booking:
        """
        Execute booking status update to cancelled

        Args:
            booking_id: Booking ID
            buyer_id: Buyer ID

        Returns:
            Updated booking

        Raises:
            NotFoundError: Booking not found
            ForbiddenError: Not authorized to cancel this booking
            DomainError: Booking status does not allow cancellation (thrown by domain layer)
        """
        # Query booking (Fail Fast)
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Validate ownership (Fail Fast)
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        # Mark as cancelled status (domain will validate state transition)
        cancelled_booking = booking.cancel()
        updated_booking = await self.booking_command_repo.update_status_to_cancelled(
            booking=cancelled_booking
        )

        # Query related tickets (via seat_positions)
        tickets = await self.booking_command_repo.get_tickets_by_booking_id(booking_id=booking_id)
        ticket_ids = [ticket.id for ticket in tickets if ticket.id]

        # Get seat position information (construct complete seat identifiers from tickets)
        # Format: section-subsection-row-seat (e.g., "A-1-1-1")
        seat_positions = [
            f'{ticket.section}-{ticket.subsection}-{ticket.row}-{ticket.seat}' for ticket in tickets
        ]
        Logger.base.info(
            f'🎫 [CANCEL] Found {len(seat_positions)} seat positions: {seat_positions}'
        )

        # Publish BookingCancelledEvent to Kafka (release Kvrocks seats)
        if ticket_ids:
            Logger.base.info(
                f'🔓 [CANCEL] Publishing cancellation event for {len(ticket_ids)} tickets'
            )

            cancelled_event = BookingCancelledEvent(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=booking.event_id,
                section=booking.section,
                subsection=booking.subsection,
                ticket_ids=ticket_ids,
                seat_positions=seat_positions,
                cancelled_at=datetime.now(timezone.utc),
            )

            # Calculate partition based on section/subsection
            section_index = ord(booking.section.upper()) - ord('A')
            global_index = section_index * settings.SUBSECTIONS_PER_SECTION + (
                booking.subsection - 1
            )
            partition = global_index % settings.KAFKA_TOTAL_PARTITIONS

            topic_name = KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                event_id=booking.event_id
            )
            await publish_domain_event(
                event=cancelled_event,
                topic=topic_name,
                partition=partition,
            )

            Logger.base.info(f'✅ [CANCEL] Published BookingCancelledEvent to {topic_name}')

        Logger.base.info(f'🎯 [CANCEL] Booking {booking_id} cancelled successfully')
        return updated_booking
