"""
Booking Kafka Consumer - 處理來自 Event-Ticketing Service 的票務預留結果
"""

import asyncio
import json
from typing import Any, Dict, Optional

from kafka import KafkaConsumer
import msgpack

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_query_repo import BookingQueryRepo
from src.booking.use_case.command.create_booking_use_case import CreateBookingUseCase
from src.booking.use_case.command.update_booking_status_to_pending_payment_use_case import (
    UpdateBookingToPendingPaymentUseCase,
)
from src.shared.config.core_setting import settings
from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_booking_command_repo, get_booking_query_repo


class BookingKafkaConsumer:
    def __init__(self):
        self.consumer: Optional[KafkaConsumer] = None
        self.create_booking_use_case: Optional[CreateBookingUseCase] = None
        self.update_pending_payment_use_case: Optional[UpdateBookingToPendingPaymentUseCase] = None
        self.booking_command_repo: Optional[BookingCommandRepo] = None
        self.booking_query_repo: Optional[BookingQueryRepo] = None
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

            session = await get_async_session().__anext__()  # Get session
            booking_command_repo = get_booking_command_repo(session)
            booking_query_repo = get_booking_query_repo(session)

            self.create_booking_use_case = CreateBookingUseCase(
                session=session,
                booking_command_repo=booking_command_repo,
            )

            self.update_pending_payment_use_case = UpdateBookingToPendingPaymentUseCase(
                session=session,
                booking_command_repo=booking_command_repo,
            )

            # Store session and repos for direct use in consumer
            self.session = session
            self.booking_command_repo = booking_command_repo
            self.booking_query_repo = booking_query_repo

            self.running = True
            Logger.base.info('Booking Kafka consumer started')

            # Start consuming messages
            await self._consume_messages()

        except Exception as e:
            Logger.base.error(f'Failed to start Kafka consumer: {e}')
            raise

    @Logger.io
    async def stop(self):
        self.running = False
        if self.consumer:
            self.consumer.close()
        Logger.base.info('Booking Kafka consumer stopped')

    @Logger.io
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

    @Logger.io
    async def _handle_tickets_reserved(self, event_data: Dict[str, Any]):
        try:
            data = event_data.get('data', {})
            buyer_id = data.get('buyer_id')
            booking_id = data.get('booking_id')
            ticket_ids = data.get('ticket_ids', [])

            if not all([buyer_id, booking_id, ticket_ids]):
                Logger.base.error('Missing required fields in tickets reserved event')
                return

            # Ensure use case is initialized
            if not self.create_booking_use_case:
                Logger.base.error('CreateBookingUseCase not initialized')
                return

            # Get the existing booking
            if not self.booking_query_repo:
                Logger.base.error('BookingQueryRepo not initialized')
                return

            booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                Logger.base.error(f'Booking {booking_id} not found')
                return

            # Verify booking belongs to the buyer
            if booking.buyer_id != buyer_id:
                Logger.base.error(f'Booking {booking_id} does not belong to buyer {buyer_id}')
                return

            # Update booking status from PROCESSING to PENDING_PAYMENT
            if not self.update_pending_payment_use_case:
                Logger.base.error('UpdateBookingToPendingPaymentUseCase not initialized')
                return

            await self.update_pending_payment_use_case.update_to_pending_payment(booking)

            Logger.base.info(f'Updated booking {booking_id} status to pending_payment')

        except Exception as e:
            Logger.base.error(f'Error handling tickets reserved: {e}')

    @Logger.io
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


@Logger.io
async def start_booking_consumer():
    global _booking_consumer
    if _booking_consumer is None:
        _booking_consumer = BookingKafkaConsumer()
    await _booking_consumer.start()


@Logger.io
async def stop_booking_consumer():
    global _booking_consumer
    if _booking_consumer:
        await _booking_consumer.stop()
        _booking_consumer = None


@Logger.io
def get_booking_consumer() -> BookingKafkaConsumer:
    global _booking_consumer
    if _booking_consumer is None:
        _booking_consumer = BookingKafkaConsumer()
    return _booking_consumer
