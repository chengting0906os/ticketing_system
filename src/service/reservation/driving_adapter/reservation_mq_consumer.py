"""
Seat Reservation Consumer - Unified Command Router

Responsibility: Manage Kvrocks seat state via unified ticket-command-request topic.

Features:
- Fully async concurrent processing via AIOConsumer
- Message-type-based routing (message_type field in proto)
- Dead Letter Queue: Failed messages sent to DLQ

Listens to 1 Topic (unified for ordering - no race condition):
- ticket-command-request: Routes by message_type field
  - BookingCreatedDomainEvent: Reserve seats (AVAILABLE → RESERVED)
  - BookingCancelledEvent: Release seats (RESERVED → AVAILABLE)

Note: Kvrocks only tracks AVAILABLE/RESERVED states. PostgreSQL is source of truth for SOLD status.
"""

import os
from typing import Any, Awaitable, Callable, Dict, Optional

from confluent_kafka import Message
import orjson

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.base_kafka_consumer import BaseKafkaConsumer
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.message_queue.proto import domain_event_pb2 as pb
from src.platform.observability.tracing import extract_trace_context
from src.service.reservation.app.dto import (
    ReleaseSeatsBatchRequest,
    ReservationRequest,
)


class ReservationConsumer(BaseKafkaConsumer):
    """
    Seat Reservation Consumer - Unified Command Router

    Listens to 1 Topic (unified for ordering - no race condition):
    - ticket-command-request: Routes by message_type field in proto

    Message Types:
    - BookingCreatedDomainEvent: Reserve seats
    - BookingCancelledEvent: Release seats

    Note: Kvrocks only tracks AVAILABLE/RESERVED states.
    PostgreSQL is source of truth for SOLD/COMPLETED status.
    """

    # Sequential processing to prevent race conditions in seat reservation
    MAX_CONCURRENT_TASKS: int = 1

    def __init__(self) -> None:
        event_id = int(os.getenv('EVENT_ID', '1'))
        consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.reservation_service(event_id=event_id),
        )
        dlq_topic = KafkaTopicBuilder.reservation_dlq(event_id=event_id)

        super().__init__(
            service_name='RESERVATION',
            consumer_group_id=consumer_group_id,
            event_id=event_id,
            dlq_topic=dlq_topic,
        )

        # Use cases (lazy initialization)
        self.seat_reservation_use_case: Any = None
        self.seat_release_use_case: Any = None

        # Unified topic for reserve/release commands
        self.command_topic = KafkaTopicBuilder.ticket_command_request(event_id=event_id)

    async def _initialize_dependencies(self) -> None:
        """Initialize use cases from DI container."""
        self.seat_reservation_use_case = container.seat_reservation_use_case()
        self.seat_release_use_case = container.seat_release_use_case()

    def _get_topic_handlers(
        self,
    ) -> Dict[str, tuple[type, Callable[[Dict], Awaitable[Any]]]]:
        """Return topic to async handler mapping.

        Note: proto_class and handler are placeholders.
        Actual routing is done in _process_message based on message_type field.
        """
        return {
            self.command_topic: (
                pb.BookingCreatedDomainEvent,  # Placeholder, actual type from body
                self._handle_reservation,  # Placeholder, actual handler from body
            ),
        }

    def _detect_message_type_and_parse(self, msg_bytes: bytes) -> tuple[str, type, Dict]:
        """
        Detect message type and parse the correct proto message.

        Since AIOProducer doesn't support headers, message_type is embedded
        in the proto message body. We try parsing each type.

        Returns: (message_type, proto_class, parsed_data)
        """
        from google.protobuf.json_format import MessageToDict

        # Try BookingCreatedDomainEvent first
        try:
            created_msg = pb.BookingCreatedDomainEvent()
            created_msg.ParseFromString(msg_bytes)
            if created_msg.message_type == 'BookingCreatedDomainEvent':
                data = MessageToDict(created_msg, preserving_proto_field_name=True)
                return ('BookingCreatedDomainEvent', pb.BookingCreatedDomainEvent, data)
        except Exception:
            pass

        # Try BookingCancelledEvent
        try:
            cancelled_msg = pb.BookingCancelledEvent()
            cancelled_msg.ParseFromString(msg_bytes)
            if cancelled_msg.message_type == 'BookingCancelledEvent':
                data = MessageToDict(cancelled_msg, preserving_proto_field_name=True)
                return ('BookingCancelledEvent', pb.BookingCancelledEvent, data)
        except Exception:
            pass

        raise ValueError('Could not detect message_type from proto body')

    async def _process_message(
        self,
        msg: Message,
        proto_class: type,  # Ignored - determined by message body
        handler: Callable[[Dict], Awaitable[Any]],  # Ignored - determined by message body
        topic: str,
    ) -> None:
        """
        Override base class to implement message-type-based routing.

        Reads message_type field from proto body to determine:
        - BookingCreatedDomainEvent → reserve seats
        - BookingCancelledEvent → release seats
        """
        try:
            # Detect message type from proto body
            msg_bytes = msg.value()
            message_type, _, data = self._detect_message_type_and_parse(msg_bytes)
            booking_id = data.get('booking_id', 'unknown')

            # Route based on message type
            if message_type == 'BookingCreatedDomainEvent':
                actual_handler = self._handle_reservation
            elif message_type == 'BookingCancelledEvent':
                actual_handler = self._handle_release
            else:
                raise ValueError(f'Unknown message_type: {message_type}')

            Logger.base.info(
                f'[RESERVATION-{self.instance_id}] type={message_type} booking_id={booking_id}'
            )

            # Extract trace context from message
            extract_trace_context(
                headers={
                    'traceparent': data.get('traceparent', ''),
                    'tracestate': data.get('tracestate', ''),
                }
            )

            # Call handler with tracing
            with self.tracer.start_as_current_span(
                f'consumer.{topic}',
                attributes={
                    'messaging.system': 'kafka',
                    'messaging.destination': topic,
                    'messaging.message_type': message_type,
                    'booking.id': booking_id,
                },
            ):
                await actual_handler(data)
                self._track_offset(msg)

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Error: {e}')

            try:
                # Try to get some data for DLQ
                data = {'raw': msg.value().hex() if msg.value() else 'empty'}
            except Exception:
                data = {'error': 'Failed to extract message data'}

            await self._send_to_dlq(message=data, original_topic=topic, error=str(e))
            self._track_offset(msg)  # Still track to avoid reprocessing

    # ========== Async Message Handlers ==========

    async def _handle_reservation(self, message: Dict) -> Dict:
        """Handle reservation request (async)."""
        booking_id = message.get('booking_id', 'unknown')

        Logger.base.info(
            f'\033[94m[RESERVATION-{self.instance_id}] Processing: booking_id={booking_id}\033[0m'
        )

        await self._handle_reservation_async(message)
        return {'success': True}

    async def _handle_release(self, message: Dict) -> Dict:
        """
        Handle seat release request (async).

        Minimal message - use case fetches all details from DB:
        - booking_id: For PostgreSQL lookup
        - event_id: For topic routing

        Flow (handled by ReleaseSeatUseCase):
        1. Fetch booking from DB (get seat_positions, section, subsection, buyer_id)
        2. Update PostgreSQL (booking → CANCELLED, tickets → AVAILABLE)
        3. Release seats in Kvrocks (RESERVED → AVAILABLE)
        4. SSE broadcast

        Idempotency: Both DB update and Kvrocks release handle duplicate messages.
        """
        booking_id = message.get('booking_id', 'unknown')
        event_id = message.get('event_id', self.event_id)

        Logger.base.info(
            f'[RELEASE-{self.instance_id}] Processing release for booking={booking_id}'
        )

        # Use case fetches all details from DB (seat_positions, section, subsection, buyer_id)
        batch_request = ReleaseSeatsBatchRequest(
            booking_id=booking_id,
            event_id=event_id,
        )
        result = await self.seat_release_use_case.execute_batch(batch_request)

        return {
            'success': True,
            'released_seats': result.successful_seats,
            'failed_seats': result.failed_seats,
            'total_released': result.total_released,
        }

    # ========== Reservation Logic ==========

    async def _handle_reservation_async(self, event_data: object) -> bool:
        """Process reservation request."""
        parsed = self._parse_event_data(event_data)
        if not parsed:
            error_msg = 'Failed to parse event data'
            raise ValueError(error_msg)

        command = self._create_reservation_command(parsed)
        Logger.base.info(f'[RESERVATION] booking_id={command["booking_id"]}')

        await self._execute_reservation(command)
        return True

    def _parse_event_data(self, event_data: object) -> Optional[Dict]:
        """Parse event data to dictionary."""
        try:
            if isinstance(event_data, dict):
                return event_data
            if isinstance(event_data, str):
                return orjson.loads(event_data)
            if hasattr(event_data, '__dict__'):
                return dict(vars(event_data))

            Logger.base.error(f'Unknown event data type: {type(event_data)}')
            return None

        except Exception as e:
            Logger.base.error(f'Parse failed: {e}')
            return None

    def _create_reservation_command(self, event_data: Dict) -> Dict:
        """Create reservation command from event data."""
        booking_id = event_data.get('booking_id')
        buyer_id = event_data.get('buyer_id')
        event_id = event_data.get('event_id')

        if not all([booking_id, buyer_id, event_id]):
            raise ValueError('Missing required fields in event data')

        return {
            'booking_id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'section': event_data['section'],
            'subsection': event_data['subsection'],
            'quantity': event_data['quantity'],
            'seat_selection_mode': event_data['seat_selection_mode'],
            'seat_positions': event_data.get('seat_positions', []),
        }

    async def _execute_reservation(self, command: Dict) -> bool:
        """Execute reservation use case."""
        request = ReservationRequest(
            booking_id=command['booking_id'],
            buyer_id=command['buyer_id'],
            event_id=command['event_id'],
            selection_mode=command['seat_selection_mode'],
            quantity=command['quantity'],
            seat_positions=command['seat_positions'],
            section_filter=command['section'],
            subsection_filter=command['subsection'],
        )

        # Call use case (use case is responsible for sending success/failure events)
        await self.seat_reservation_use_case.reserve_seats(request)
        return True
