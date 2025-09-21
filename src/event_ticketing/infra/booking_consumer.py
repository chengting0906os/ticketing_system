"""
Event Ticketing Kafka Consumer - 處理來自 Booking Service 的訂票請求
"""

import asyncio
import json
from typing import Any, Dict

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
            from src.shared.service.unit_of_work import get_unit_of_work

            uow = get_unit_of_work()
            self.reserve_tickets_use_case = ReserveTicketsUseCase(uow=uow)  # type: ignore

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

                for _, messages in message_batch.items():
                    for message in messages:
                        await self._process_message(message)

                # Commit offsets
                self.consumer.commit()  # type: ignore

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)

            except Exception as e:
                Logger.base.error(f'Error consuming messages: {e}')
                await asyncio.sleep(1)  # Wait before retrying

    @Logger.io
    async def _process_message(self, message):
        """Process a single Kafka message"""
        try:
            # Deserialize message
            event_data = self._deserialize_message(message.value)
            event_type = event_data.get('event_type')

            Logger.base.info(f'Processing event: {event_type}')

            # Route to appropriate handler
            if event_type == 'BookingRequested':
                await self._handle_booking_request(event_data)
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
    async def _handle_booking_request(self, event_data: Dict[str, Any]):
        """Handle booking request event"""
        try:
            # Extract booking request data
            data = event_data.get('data', {})
            buyer_id = data.get('buyer_id')
            event_id = data.get('event_id')
            ticket_count = data.get('ticket_count')
            request_id = data.get('request_id')  # For correlation

            if not all([buyer_id, event_id, ticket_count, request_id]):
                Logger.base.error('Missing required fields in booking request')
                await self._send_booking_failed_event(request_id, 'Missing required fields')
                return

            # Reserve tickets
            try:
                reservation_result = await self.reserve_tickets_use_case.reserve_tickets(  # type: ignore
                    event_id=event_id, ticket_count=ticket_count, buyer_id=buyer_id
                )

                # Send success event back to booking service
                await self._send_booking_success_event(request_id, reservation_result)

            except Exception as e:
                Logger.base.error(f'Failed to reserve tickets: {e}')
                await self._send_booking_failed_event(request_id, str(e))

        except Exception as e:
            Logger.base.error(f'Error handling booking request: {e}')

    @Logger.io
    async def _send_booking_success_event(self, request_id: str, reservation_data: Dict[str, Any]):
        """Send booking success event back to booking service"""
        event = {
            'event_type': 'TicketsReserved',
            'aggregate_id': reservation_data.get('reservation_id'),
            'data': {
                'request_id': request_id,
                'reservation_id': reservation_data.get('reservation_id'),
                'buyer_id': reservation_data.get('buyer_id'),
                'ticket_count': reservation_data.get('ticket_count'),
                'tickets': reservation_data.get('tickets', []),
                'status': 'reserved',
            },
        }

        # Use subsection-based partition key for proper ordering
        tickets = reservation_data.get('tickets', [])
        if tickets:
            # Assume all tickets are from same event/section (business rule)
            # Use event_id-section-subsection as partition key
            event_id = reservation_data.get('event_id') or 'unknown'
            section = tickets[0].get('section', 'unknown')
            subsection = tickets[0].get('subsection', '1')
            partition_key = f'{event_id}-{section}-{subsection}'
        else:
            partition_key = request_id

        await publish_domain_event(
            event=event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_RESPONSE,
            partition_key=partition_key,  # type: ignore
        )

        Logger.base.info(f'Sent booking success event for request {request_id}')

    @Logger.io
    async def _send_booking_failed_event(self, request_id: str, error_message: str):
        """Send booking failure event back to booking service"""
        event = {
            'event_type': 'TicketReservationFailed',
            'aggregate_id': 0,  # No reservation created
            'data': {'request_id': request_id, 'error_message': error_message, 'status': 'failed'},
        }

        await publish_domain_event(
            event=event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_RESPONSE,
            partition_key=request_id,  # type: ignore
        )

        Logger.base.info(f'Sent booking failure event for request {request_id}')


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
