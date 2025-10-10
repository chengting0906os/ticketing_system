from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import Depends

from src.platform.database.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingCancelledEvent
from src.service.ticketing.domain.entity.booking_entity import BookingStatus


class CancelBookingUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def cancel_booking(self, *, booking_id: int, buyer_id: int) -> Dict[str, Any]:
        async with self.uow:
            # Get the booking first to verify ownership and status
            booking = await self.uow.booking_query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                raise NotFoundError('Booking not found')

            # Verify booking belongs to requesting buyer
            if booking.buyer_id != buyer_id:
                raise ForbiddenError('Only the buyer can cancel this booking')

            # Check if booking can be cancelled
            if booking.status == BookingStatus.COMPLETED:
                raise DomainError('Cannot cancel completed booking', 400)
            elif booking.status == BookingStatus.CANCELLED:
                raise DomainError('Booking already cancelled', 400)

            # Cancel the booking
            cancelled_booking = booking.cancel()
            updated_booking = await self.uow.booking_command_repo.update_status_to_cancelled(
                booking=cancelled_booking
            )

            # Query ticket_ids from association table BEFORE commit
            ticket_ids = await self.uow.booking_command_repo.get_ticket_ids_by_booking_id(
                booking_id=booking_id
            )

            # Get seat positions for seat release
            seat_positions = []
            if ticket_ids:
                # Get ticket details to extract seat positions
                tickets = await self.uow.event_ticketing_query_repo.get_tickets_by_ids(
                    ticket_ids=ticket_ids
                )
                # Extract seat identifiers, filtering out any None values
                seat_positions = [
                    ticket.seat_identifier
                    for ticket in tickets
                    if ticket.seat_identifier is not None
                ]
                Logger.base.info(
                    f'🎫 [CANCEL] Found {len(seat_positions)} seat positions: {seat_positions}'
                )

            # UoW commits!
            await self.uow.commit()

        if ticket_ids:
            Logger.base.info(
                f'🔓 [CANCEL] Publishing cancellation event for {len(ticket_ids)} tickets in booking {booking_id}'
            )

            cancelled_event = BookingCancelledEvent(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=booking.event_id,
                ticket_ids=ticket_ids,
                seat_positions=seat_positions,  # Now properly populated
                cancelled_at=datetime.now(timezone.utc),
            )

            # Publish to seat_reservation service to release seats in Kvrocks
            topic_name = KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                event_id=booking.event_id
            )
            partition_key = f'event-{booking.event_id}'

            await publish_domain_event(
                event=cancelled_event, topic=topic_name, partition_key=partition_key
            )

            Logger.base.info(
                f'✅ [CANCEL] Published BookingCancelledEvent to release seats in Kvrocks: {topic_name}'
            )

        Logger.base.info(f'🎯 [CANCEL] Booking {booking_id} cancelled successfully')

        return {
            'status': 'ok',
            'cancelled_tickets': len(ticket_ids) if ticket_ids else 0,
            'booking_id': updated_booking.id,
        }
