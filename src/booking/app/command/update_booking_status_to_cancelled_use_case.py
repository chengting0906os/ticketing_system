from typing import Any, Dict

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.app.interface.i_booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_domain_events import BookingCancelledEvent
from src.booking.domain.booking_entity import BookingStatus
from src.booking.app.interface.i_booking_query_repo import BookingQueryRepo
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder


class CancelBookingUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
        booking_query_repo: BookingQueryRepo,
    ):
        self.session = session
        self.booking_command_repo = booking_command_repo
        self.booking_query_repo = booking_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
        booking_query_repo: BookingQueryRepo = Depends(Provide[Container.booking_query_repo]),
    ):
        return cls(
            session=session,
            booking_command_repo=booking_command_repo,
            booking_query_repo=booking_query_repo,
        )

    @Logger.io
    async def cancel_booking(self, *, booking_id: int, buyer_id: int) -> Dict[str, Any]:
        # Get the booking first to verify ownership and status
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Verify booking belongs to requesting buyer
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        # Check if booking can be cancelled
        if booking.status == BookingStatus.PAID:
            raise DomainError('Cannot cancel paid booking', 400)
        elif booking.status == BookingStatus.CANCELLED:
            raise DomainError('Booking already cancelled', 400)

        # Cancel the booking
        cancelled_booking = booking.cancel()
        updated_booking = await self.booking_command_repo.update_status_to_cancelled(
            booking=cancelled_booking
        )

        # Publish domain event for event_ticketing service to handle ticket release
        if booking.ticket_ids:
            Logger.base.info(
                f'🔓 [CANCEL] Publishing cancellation event for {len(booking.ticket_ids)} tickets in booking {booking_id}'
            )

            # Extract ticket IDs from booking
            ticket_ids = [ticket_id for ticket_id in booking.ticket_ids if ticket_id is not None]

            if ticket_ids:
                # Create and publish BookingCancelledEvent
                from datetime import datetime, timezone

                cancelled_event = BookingCancelledEvent(
                    booking_id=booking_id,
                    buyer_id=buyer_id,
                    event_id=booking.event_id,
                    ticket_ids=ticket_ids,
                    cancelled_at=datetime.now(timezone.utc),
                )

                # Publish to event_ticketing service according to README pattern
                topic_name = KafkaTopicBuilder.update_ticket_status_to_available_in_kvrocks(
                    event_id=booking.event_id
                )
                partition_key = f'event-{booking.event_id}'

                await publish_domain_event(
                    event=cancelled_event, topic=topic_name, partition_key=partition_key
                )

                Logger.base.info(
                    f'✅ [CANCEL] Published BookingCancelledEvent to topic: {topic_name}'
                )

        await self.session.commit()
        Logger.base.info(f'🎯 [CANCEL] Booking {booking_id} cancelled successfully')

        return {
            'status': 'ok',
            'cancelled_tickets': len(booking.ticket_ids),
            'booking_id': updated_booking.id,
        }
