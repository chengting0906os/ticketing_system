"""
Seat Reservation Consumer - Seat Selection Router
Responsibility: Manage Kvrocks seat state and handle reservation requests

Features:
- Fully async concurrent processing via AIOConsumer
- Retry mechanism: Exponential backoff
- Dead Letter Queue: Failed messages sent to DLQ

Uses confluent-kafka experimental AIOConsumer for async message processing.
"""

import os
from typing import Any, Awaitable, Callable, Dict, Optional

import orjson

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.base_kafka_consumer import BaseKafkaConsumer
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.message_queue.proto import domain_event_pb2 as pb
from src.service.reservation.app.dto import (
    FinalizeSeatPaymentRequest,
    ReservationRequest,
)
from src.service.shared_kernel.app.dto import ReleaseSeatsBatchRequest
from src.service.shared_kernel.domain.value_object import SubsectionConfig


class SeatReservationConsumer(BaseKafkaConsumer):
    """
    Seat Reservation Consumer - Stateless Router

    Listens to 3 Topics:
    1. booking_to_reservation_reserve_seats - Reservation requests
    2. release_ticket_status_to_available_in_kvrocks - Release seats
    3. finalize_ticket_status_to_paid_in_kvrocks - Finalize payment

    Uses confluent-kafka AIOConsumer for async message processing.
    """

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
        self.reserve_seats_use_case: Any = None
        self.release_seat_use_case: Any = None
        self.finalize_seat_payment_use_case: Any = None

        # Topic names
        self.reservation_topic = KafkaTopicBuilder.booking_to_reservation_reserve_seats(
            event_id=event_id
        )
        self.release_topic = KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
            event_id=event_id
        )
        self.finalize_topic = KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(
            event_id=event_id
        )

    async def _initialize_dependencies(self) -> None:
        """Initialize use cases from DI container."""
        self.reserve_seats_use_case = container.reserve_seats_use_case()
        self.release_seat_use_case = container.release_seat_use_case()
        self.finalize_seat_payment_use_case = container.finalize_seat_payment_use_case()

    def _get_topic_handlers(
        self,
    ) -> Dict[str, tuple[type, Callable[[Dict], Awaitable[Any]]]]:
        """Return topic to async handler mapping."""
        return {
            self.reservation_topic: (
                pb.ReservationRequestEvent,
                self._handle_reservation,
            ),
            self.release_topic: (
                pb.BookingCancelledEvent,
                self._handle_release,
            ),
            self.finalize_topic: (
                pb.BookingPaidEvent,
                self._handle_finalize,
            ),
        }

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
        """Handle seat release request (async)."""
        seat_positions = message.get('seat_positions', [])

        if not seat_positions:
            error_msg = 'Missing seat_positions'
            Logger.base.error(f'[RELEASE] {error_msg}')
            raise ValueError(error_msg)

        booking_id = message.get('booking_id', 'unknown')
        event_id = message.get('event_id', self.event_id)

        Logger.base.info(
            f'[RELEASE-{self.instance_id}] Releasing {len(seat_positions)} seats for booking={booking_id}'
        )

        batch_request = ReleaseSeatsBatchRequest(seat_ids=seat_positions, event_id=event_id)
        result = await self.release_seat_use_case.execute_batch(batch_request)

        return {
            'success': True,
            'released_seats': result.successful_seats,
            'failed_seats': result.failed_seats,
            'total_released': result.total_released,
        }

    async def _handle_finalize(self, message: Dict) -> Dict:
        """Handle payment finalization request (async)."""
        seat_positions = message.get('seat_positions', [])

        if not seat_positions:
            error_msg = 'Missing seat_positions'
            Logger.base.error(f'[FINALIZE] {error_msg}')
            raise ValueError(error_msg)

        booking_id = message.get('booking_id', 'unknown')
        event_id = message.get('event_id', self.event_id)
        successful_seats = []
        failed_seats = []

        for seat_id in seat_positions:
            request = FinalizeSeatPaymentRequest(
                seat_id=seat_id,
                event_id=event_id,
            )
            result = await self.finalize_seat_payment_use_case.execute(request)
            if result.success:
                successful_seats.append(seat_id)
            else:
                failed_seats.append(seat_id)

        Logger.base.info(
            f'[FINALIZE-{self.instance_id}] booking_id={booking_id} '
            f'success={len(successful_seats)}, failed={len(failed_seats)}'
        )

        return {
            'success': len(failed_seats) == 0,
            'successful_seats': successful_seats,
            'failed_seats': failed_seats,
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
        config = event_data['config']

        return {
            'booking_id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'section': event_data['section'],
            'subsection': event_data['subsection'],
            'quantity': event_data['quantity'],
            'seat_selection_mode': event_data['seat_selection_mode'],
            'seat_positions': event_data.get('seat_positions', []),
            'rows': config.get('rows', 0),
            'cols': config.get('cols', 0),
            'price': config.get('price', 0),
        }

    async def _execute_reservation(self, command: Dict) -> bool:
        """Execute reservation use case."""
        config = SubsectionConfig(
            rows=command['rows'],
            cols=command['cols'],
            price=command['price'],
        )

        request = ReservationRequest(
            booking_id=command['booking_id'],
            buyer_id=command['buyer_id'],
            event_id=command['event_id'],
            selection_mode=command['seat_selection_mode'],
            quantity=command['quantity'],
            seat_positions=command['seat_positions'],
            section_filter=command['section'],
            subsection_filter=command['subsection'],
            config=config,
        )

        # Call use case (use case is responsible for sending success/failure events)
        await self.reserve_seats_use_case.reserve_seats(request)
        return True
