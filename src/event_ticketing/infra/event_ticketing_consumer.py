"""
Event Ticketing Kafka Consumer - 處理來自 Booking Service 的訂票請求
"""

import asyncio
import json
from typing import Any, Dict, List

from kafka import KafkaConsumer
import msgpack

from src.event_ticketing.use_case.reserve_tickets_use_case import ReserveTicketsUseCase
from src.shared.config.core_setting import settings
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_publisher import publish_domain_event
from src.shared.logging.loguru_io import Logger


class TicketingKafkaConsumer:
    """Kafka consumer for event-ticketing service"""

    def __init__(self):
        self.consumer = None
        self.reserve_tickets_use_case = None
        self.running = False

    @Logger.io
    async def start(self):
        """Start the Kafka consumer"""
        try:
            # Initialize consumer
            self.consumer = KafkaConsumer(
                Topic.TICKETING_BOOKING_REQUEST,  # Topic for booking requests
                **settings.KAFKA_CONSUMER_CONFIG,  # type: ignore
                value_deserializer=None,  # We handle deserialization ourselves
            )

            # Get use case dependency
            from src.shared.config.db_setting import get_async_session
            from src.shared.service.repo_di import get_ticket_repo

            session = await get_async_session().__anext__()
            ticket_repo = get_ticket_repo(session)
            self.reserve_tickets_use_case = ReserveTicketsUseCase(
                session=session,
                ticket_repo=ticket_repo,
            )

            self.running = True
            Logger.base.info('Event-Ticketing Kafka consumer started')

            # Start consuming messages
            await self._consume_messages()

        except Exception as e:
            Logger.base.error(f'Failed to start Kafka consumer: {e}')
            raise

    @Logger.io
    async def stop(self):
        """Stop the Kafka consumer"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        Logger.base.info('Event-Ticketing Kafka consumer stopped')

    @Logger.io
    async def _consume_messages(self):
        while self.running:
            try:
                # Poll for messages (non-blocking)
                message_batch = self.consumer.poll(timeout_ms=100)  # type: ignore

                if message_batch:
                    for _, messages in message_batch.items():
                        for message in messages:
                            await self._process_message(message)

                    # Commit offsets after processing all messages
                    self.consumer.commit()  # type: ignore

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)

            except Exception as e:
                Logger.base.error(f'Error consuming messages: {e}')
                await asyncio.sleep(1)  # Wait before retrying  # Wait before retrying

    @Logger.io
    async def _process_message(self, message):
        """Process a single Kafka message"""
        try:
            # Deserialize message
            event_data = self._deserialize_message(message.value)
            event_type = event_data.get('event_type')

            Logger.base.info(f'Processing event: {event_type}')

            # Route to appropriate handler
            if event_type == 'BookingCreated':
                await self._handle_booking_created(event_data)
            else:
                Logger.base.warning(f'Unknown event type: {event_type}')

        except Exception as e:
            Logger.base.error(f'Error processing message: {e}')

    def _deserialize_message(self, raw_value: bytes) -> Dict[str, Any]:
        """Deserialize Kafka message value"""
        try:
            # Try MessagePack first
            return msgpack.unpackb(raw_value, raw=False)
        except Exception:
            try:
                # Fallback to JSON
                return json.loads(raw_value.decode('utf-8'))
            except Exception as e:
                raise ValueError(f'Failed to deserialize message: {e}')

    @Logger.io
    async def _handle_booking_created(self, event_data: Dict[str, Any]):
        """Handle BookingCreated event"""
        try:
            # Extract booking data from BookingCreated event
            aggregate_id = event_data.get('aggregate_id')  # This is the booking_id
            buyer_id = event_data.get('buyer_id')
            event_id = event_data.get('event_id')

            if not aggregate_id or not buyer_id or not event_id:
                Logger.base.error('Missing required fields in BookingCreated event')
                await self._send_booking_failed_event(
                    str(aggregate_id or 0), 'Missing required fields'
                )
                return

            # Get the booking to extract ticket_ids
            from src.event_ticketing.use_case.validate_tickets_use_case import (
                ValidateTicketsUseCase,
            )
            from src.shared.config.db_setting import get_async_session
            from src.shared.service.repo_di import get_booking_repo, get_ticket_repo

            booking_repo = get_booking_repo()
            ticket_repo = get_ticket_repo()
            session_gen = get_async_session()
            session = await session_gen.__anext__()

            try:
                booking = await booking_repo.get_by_id(booking_id=aggregate_id)
                if not booking or not booking.ticket_ids:
                    Logger.base.error(f'Booking {aggregate_id} not found or has no ticket_ids')
                    await self._send_booking_failed_event(
                        str(aggregate_id), 'Booking not found or invalid'
                    )
                    return

                # Use ValidateTicketsUseCase to reserve the specific tickets
                validate_use_case = ValidateTicketsUseCase(session=session, ticket_repo=ticket_repo)
                await validate_use_case.reserve_tickets(
                    ticket_ids=booking.ticket_ids, buyer_id=buyer_id
                )

                # Send success event back to booking service
                await self._send_booking_success_event(
                    booking_id=aggregate_id, buyer_id=buyer_id, ticket_ids=booking.ticket_ids
                )

            except Exception as e:
                Logger.base.error(f'Failed to reserve tickets for booking {aggregate_id}: {e}')
                await self._send_booking_failed_event(str(aggregate_id), str(e))
            finally:
                await session.close()

        except Exception as e:
            Logger.base.error(f'Error handling BookingCreated event: {e}')

    @Logger.io
    async def _send_booking_success_event(
        self, booking_id: int, buyer_id: int, ticket_ids: List[int]
    ):
        """Send booking success event back to booking service"""
        event = {
            'event_type': 'TicketsReserved',
            'aggregate_id': booking_id,
            'data': {
                'booking_id': booking_id,  # Include booking_id for the consumer
                'buyer_id': buyer_id,
                'ticket_ids': ticket_ids,
                'status': 'reserved',
            },
        }

        # Use booking_id as partition key for proper ordering
        partition_key = str(booking_id)

        await publish_domain_event(
            event=event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_RESPONSE,
            partition_key=partition_key,  # type: ignore
        )

        Logger.base.info(f'Sent TicketsReserved event for booking {booking_id}')

    @Logger.io
    async def _send_booking_failed_event(self, booking_id: str, error_message: str):
        """Send booking failure event back to booking service"""
        event = {
            'event_type': 'TicketReservationFailed',
            'aggregate_id': booking_id,
            'data': {'booking_id': booking_id, 'error_message': error_message, 'status': 'failed'},
        }

        await publish_domain_event(
            event=event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_RESPONSE,
            partition_key=booking_id,  # type: ignore
        )

        Logger.base.info(f'Sent TicketReservationFailed event for booking {booking_id}')


# Global consumer instance
_ticketing_consumer = None


@Logger.io
async def start_ticketing_consumer():
    """Start the global ticketing consumer"""
    global _ticketing_consumer
    if _ticketing_consumer is None:
        _ticketing_consumer = TicketingKafkaConsumer()
    await _ticketing_consumer.start()


@Logger.io
async def stop_ticketing_consumer():
    """Stop the global ticketing consumer"""
    global _ticketing_consumer
    if _ticketing_consumer:
        await _ticketing_consumer.stop()
        _ticketing_consumer = None


@Logger.io
def get_ticketing_consumer() -> TicketingKafkaConsumer:
    """Get the global consumer instance"""
    global _ticketing_consumer
    if _ticketing_consumer is None:
        _ticketing_consumer = TicketingKafkaConsumer()
    return _ticketing_consumer
