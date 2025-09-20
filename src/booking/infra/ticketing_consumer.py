"""
Booking Kafka Consumer - 處理來自 Event-Ticketing Service 的票務預留結果
"""

import asyncio
import json
from typing import Any, Dict

from kafka import KafkaConsumer
import msgpack

from src.booking.use_case.create_booking_use_case import CreateBookingUseCase
from src.shared.config.core_setting import settings
from src.shared.constant.topic import Topic
from src.shared.logging.loguru_io import Logger


class BookingKafkaConsumer:
    def __init__(self):
        self.consumer = None
        self.create_booking_use_case = None
        self.running = False

    async def start(self):
        """Start the Kafka consumer"""
        try:
            # Initialize consumer
            self.consumer = KafkaConsumer(
                Topic.TICKETING_BOOKING_RESPONSE,
                **settings.KAFKA_CONSUMER_CONFIG,  # type: ignore
                value_deserializer=None,
            )

            # Get use case dependency
            from src.shared.config.db_setting import get_async_session
            from src.shared.service.repo_di import (
                get_booking_repo,
                get_event_repo,
                get_ticket_repo,
                get_user_repo,
            )

            session = await get_async_session().__anext__()  # Get session
            booking_repo = get_booking_repo()
            user_repo = get_user_repo()
            ticket_repo = get_ticket_repo()
            event_repo = get_event_repo()

            self.create_booking_use_case = CreateBookingUseCase(
                session=session,
                booking_repo=booking_repo,
                user_repo=user_repo,
                ticket_repo=ticket_repo,
                event_repo=event_repo,
            )

            self.running = True
            Logger.base.info('Booking Kafka consumer started')

            # Start consuming messages
            await self._consume_messages()

        except Exception as e:
            Logger.base.error(f'Failed to start Kafka consumer: {e}')
            raise

    async def stop(self):
        self.running = False
        if self.consumer:
            self.consumer.close()
        Logger.base.info('Booking Kafka consumer stopped')

    async def _consume_messages(self):
        while self.running:
            try:
                # Poll for messages (non-blocking)
                message_batch = self.consumer.poll(timeout_ms=100)  # type: ignore

                for _topic_partition, messages in message_batch.items():
                    for message in messages:
                        await self._process_message(message)

                # Commit offsets
                self.consumer.commit()  # type: ignore

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)

            except Exception as e:
                Logger.base.error(f'Error consuming messages: {e}')
                await asyncio.sleep(1)  # Wait before retrying

    async def _process_message(self, message):
        try:
            # Deserialize message
            event_data = self._deserialize_message(message.value)
            event_type = event_data.get('event_type')
            Logger.base.info(f'Processing event: {event_type}')

            # Route to appropriate handler
            if event_type == 'TicketsReserved':
                await self._handle_tickets_reserved(event_data)
            elif event_type == 'TicketReservationFailed':
                await self._handle_reservation_failed(event_data)
            else:
                Logger.base.warning(f'Unknown event type: {event_type}')

        except Exception as e:
            Logger.base.error(f'Error processing message: {e}')

    def _deserialize_message(self, raw_value: bytes) -> Dict[str, Any]:
        try:
            # Try MessagePack first
            return msgpack.unpackb(raw_value, raw=False)
        except Exception:
            try:
                # Fallback to JSON
                return json.loads(raw_value.decode('utf-8'))
            except Exception as e:
                raise ValueError(f'Failed to deserialize message: {e}')

    async def _handle_tickets_reserved(self, event_data: Dict[str, Any]):
        try:
            data = event_data.get('data', {})
            request_id = data.get('request_id')
            buyer_id = data.get('buyer_id')
            tickets = data.get('tickets', [])

            if not all([request_id, buyer_id, tickets]):
                Logger.base.error('Missing required fields in tickets reserved event')
                return

            # Extract ticket IDs
            ticket_ids = [ticket['id'] for ticket in tickets]

            # Create booking with reserved tickets
            booking = await self.create_booking_use_case.create_booking(  # pyright: ignore[reportOptionalMemberAccess]
                buyer_id=buyer_id, ticket_ids=ticket_ids
            )

            Logger.base.info(f'Created booking {booking.id} for request {request_id}')

        except Exception as e:
            Logger.base.error(f'Error handling tickets reserved: {e}')

    async def _handle_reservation_failed(self, event_data: Dict[str, Any]):
        """Handle failed ticket reservation"""
        try:
            data = event_data.get('data', {})
            request_id = data.get('request_id')
            error_message = data.get('error_message')

            Logger.base.warning(
                f'Ticket reservation failed for request {request_id}: {error_message}'
            )

            # TODO: Notify user about failure
            # This could trigger email notification, update UI, etc.

        except Exception as e:
            Logger.base.error(f'Error handling reservation failed: {e}')


# Global consumer instance
_booking_consumer = None


async def start_booking_consumer():
    global _booking_consumer
    if _booking_consumer is None:
        _booking_consumer = BookingKafkaConsumer()
    await _booking_consumer.start()


async def stop_booking_consumer():
    global _booking_consumer
    if _booking_consumer:
        await _booking_consumer.stop()
        _booking_consumer = None


def get_booking_consumer() -> BookingKafkaConsumer:
    global _booking_consumer
    if _booking_consumer is None:
        _booking_consumer = BookingKafkaConsumer()
    return _booking_consumer
