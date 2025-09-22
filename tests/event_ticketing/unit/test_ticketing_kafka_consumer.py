#!/usr/bin/env python3
"""
TicketingKafkaConsumer 單元測試
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import msgpack
import pytest

from src.event_ticketing.infra.ticketing_consumer import TicketingKafkaConsumer
from src.shared.constant.topic import Topic
from src.shared.exception.exceptions import DomainError


class TestTicketingKafkaConsumer:
    """TicketingKafkaConsumer 單元測試"""

    @pytest.fixture
    def consumer(self):
        """Create TicketingKafkaConsumer instance"""
        return TicketingKafkaConsumer()

    @pytest.fixture
    def mock_reserve_use_case(self):
        """Mock ReserveTicketsUseCase"""
        use_case = AsyncMock()
        return use_case

    @pytest.fixture
    def valid_booking_request_event(self):
        """Create a valid booking request event"""
        return {
            'event_type': 'BookingRequested',
            'aggregate_id': 1,
            'data': {
                'request_id': 'test-request-123',
                'buyer_id': 1,
                'event_id': 456,
                'ticket_count': 2,
            },
        }

    @pytest.fixture
    def successful_reservation_result(self):
        """Create a successful reservation result"""
        return {
            'reservation_id': 789,
            'buyer_id': 1,
            'event_id': 456,
            'ticket_count': 2,
            'status': 'reserved',
            'tickets': [
                {
                    'id': 1001,
                    'seat_identifier': 'A-1-1-1',
                    'price': 100,
                    'section': 'A',
                    'subsection': 1,
                },
                {
                    'id': 1002,
                    'seat_identifier': 'A-1-1-2',
                    'price': 100,
                    'section': 'A',
                    'subsection': 1,
                },
            ],
        }

    def test_deserialize_message_msgpack(self, consumer):
        """測試 MessagePack 訊息反序列化"""
        # Arrange
        test_data = {'event_type': 'BookingRequested', 'data': {'test': 'value'}}
        serialized = msgpack.packb(test_data)

        # Act
        result = consumer._deserialize_message(serialized)

        # Assert
        assert result == test_data

    def test_deserialize_message_json(self, consumer):
        """測試 JSON 訊息反序列化"""
        # Arrange
        test_data = {'event_type': 'BookingRequested', 'data': {'test': 'value'}}
        serialized = json.dumps(test_data).encode('utf-8')

        # Act
        result = consumer._deserialize_message(serialized)

        # Assert
        assert result == test_data

    def test_deserialize_message_invalid(self, consumer):
        """測試無效訊息反序列化"""
        # Arrange
        invalid_data = b'invalid message'

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            consumer._deserialize_message(invalid_data)

        assert 'Failed to deserialize message' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_booking_request_success(
        self, consumer, valid_booking_request_event, successful_reservation_result
    ):
        """測試成功處理訂票請求"""
        # Arrange
        consumer.reserve_tickets_use_case = AsyncMock()
        consumer.reserve_tickets_use_case.reserve_tickets.return_value = (
            successful_reservation_result
        )

        with patch(
            'src.event_ticketing.infra.booking_consumer.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act
            await consumer._handle_booking_request(valid_booking_request_event)

            # Assert
            # Verify reserve_tickets was called with correct parameters
            consumer.reserve_tickets_use_case.reserve_tickets.assert_called_once_with(
                event_id=456, ticket_count=2, buyer_id=1
            )

            # Verify success event was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args

            # Check success event structure
            event = call_args.kwargs['event']
            assert event['event_type'] == 'TicketsReserved'
            assert event['aggregate_id'] == 789  # reservation_id
            assert event['data']['request_id'] == 'test-request-123'
            assert event['data']['status'] == 'reserved'

            # Check topic and partition key
            assert call_args.kwargs['topic'] == Topic.TICKETING_BOOKING_RESPONSE
            assert call_args.kwargs['partition_key'] == '456-A-1'  # event_id-section-subsection

    @pytest.mark.asyncio
    async def test_handle_booking_request_reservation_failure(
        self, consumer, valid_booking_request_event
    ):
        """測試票務預留失敗的情況"""
        # Arrange
        consumer.reserve_tickets_use_case = AsyncMock()
        consumer.reserve_tickets_use_case.reserve_tickets.side_effect = DomainError(
            'Not enough tickets'
        )

        with patch(
            'src.event_ticketing.infra.booking_consumer.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act
            await consumer._handle_booking_request(valid_booking_request_event)

            # Assert
            # Verify failure event was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args

            # Check failure event structure
            event = call_args.kwargs['event']
            assert event['event_type'] == 'TicketReservationFailed'
            assert event['aggregate_id'] == 0
            assert event['data']['request_id'] == 'test-request-123'
            assert event['data']['error_message'] == 'Not enough tickets'
            assert event['data']['status'] == 'failed'

    @pytest.mark.asyncio
    async def test_handle_booking_request_missing_fields(self, consumer):
        """測試缺少必要欄位的情況"""
        # Arrange
        invalid_event = {
            'event_type': 'BookingRequested',
            'data': {
                'request_id': 'test-request-123',
                # Missing buyer_id, event_id, ticket_count
            },
        }

        with patch(
            'src.event_ticketing.infra.booking_consumer.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act
            await consumer._handle_booking_request(invalid_event)

            # Assert
            # Verify failure event was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args

            event = call_args.kwargs['event']
            assert event['event_type'] == 'TicketReservationFailed'
            assert 'Missing required fields' in event['data']['error_message']

    @pytest.mark.asyncio
    async def test_process_message_unknown_event_type(self, consumer):
        """測試未知事件類型的處理"""
        # Arrange
        mock_message = MagicMock()
        mock_message.value = msgpack.packb({'event_type': 'UnknownEvent', 'data': {}})

        # Act
        await consumer._process_message(mock_message)

        # Assert - 應該記錄警告但不拋出異常
        # 這個測試主要確保程式不會因為未知事件類型而崩潰

    @pytest.mark.asyncio
    async def test_process_message_deserialization_error(self, consumer):
        """測試訊息反序列化錯誤的處理"""
        # Arrange
        mock_message = MagicMock()
        mock_message.value = b'invalid message format'

        # Act
        await consumer._process_message(mock_message)

        # Assert - 應該記錄錯誤但不拋出異常
        # 這個測試主要確保程式不會因為無效訊息而崩潰

    @pytest.mark.asyncio
    async def test_send_booking_success_event_with_partition_key(
        self, consumer, successful_reservation_result
    ):
        """測試成功事件的分區鍵生成"""
        # Arrange
        request_id = 'test-request-123'

        with patch(
            'src.event_ticketing.infra.booking_consumer.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act
            await consumer._send_booking_success_event(request_id, successful_reservation_result)

            # Assert
            call_args = mock_publish.call_args

            # Check partition key format
            partition_key = call_args.kwargs['partition_key']
            assert partition_key == '456-A-1'  # event_id-section-subsection
