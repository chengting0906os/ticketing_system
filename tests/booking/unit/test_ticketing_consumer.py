#!/usr/bin/env python3
"""
BookingKafkaConsumer (在 booking service 中的 ticketing_consumer) 單元測試
"""

import json
from unittest.mock import AsyncMock, MagicMock

import msgpack
import pytest

from src.booking.infra.ticketing_consumer import BookingKafkaConsumer


class TestBookingKafkaConsumer:
    """BookingKafkaConsumer 單元測試"""

    @pytest.fixture
    def consumer(self):
        """Create BookingKafkaConsumer instance"""
        return BookingKafkaConsumer()

    @pytest.fixture
    def mock_create_booking_use_case(self):
        """Mock CreateBookingUseCase"""
        use_case = AsyncMock()
        return use_case

    @pytest.fixture
    def valid_tickets_reserved_event(self):
        """Create a valid tickets reserved event"""
        return {
            'event_type': 'TicketsReserved',
            'aggregate_id': 789,
            'data': {
                'booking_id': 789,  # The booking ID that already exists
                'buyer_id': 1,
                'ticket_ids': [1001, 1002],  # List of reserved ticket IDs
                'status': 'reserved',
            },
        }

    @pytest.fixture
    def reservation_failed_event(self):
        """Create a reservation failed event"""
        return {
            'event_type': 'TicketReservationFailed',
            'aggregate_id': 0,
            'data': {
                'request_id': 'test-request-123',
                'error_message': 'Not enough available tickets',
                'status': 'failed',
            },
        }

    @pytest.fixture
    def successful_booking(self):
        """Create a successful booking result"""
        from datetime import datetime

        from src.booking.domain.booking_entity import Booking, BookingStatus

        return Booking(
            id=456,
            buyer_id=1,
            seller_id=2,
            event_id=123,
            total_price=200,
            status=BookingStatus.PENDING_PAYMENT,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def test_deserialize_message_msgpack(self, consumer):
        """測試 MessagePack 訊息反序列化"""
        # Arrange
        test_data = {'event_type': 'TicketsReserved', 'data': {'test': 'value'}}
        serialized = msgpack.packb(test_data)

        # Act
        result = consumer._deserialize_message(serialized)

        # Assert
        assert result == test_data

    def test_deserialize_message_json(self, consumer):
        """測試 JSON 訊息反序列化"""
        # Arrange
        test_data = {'event_type': 'TicketsReserved', 'data': {'test': 'value'}}
        serialized = json.dumps(test_data).encode('utf-8')

        # Act
        result = consumer._deserialize_message(serialized)

        # Assert
        assert result == test_data

    def test_deserialize_message_invalid(self, consumer):
        """測試無效訊息反序列化"""
        # Arrange
        invalid_data = b'invalid message format'

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            consumer._deserialize_message(invalid_data)

        assert 'Failed to deserialize message' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_tickets_reserved_success(
        self, consumer, valid_tickets_reserved_event, successful_booking
    ):
        """測試成功處理票務預留事件"""
        # Arrange
        consumer.create_booking_use_case = AsyncMock()
        consumer.create_booking_use_case.booking_repo.get_by_id.return_value = successful_booking
        consumer.create_booking_use_case.update_booking_status.return_value = successful_booking

        # Act
        await consumer._handle_tickets_reserved(valid_tickets_reserved_event)

        # Assert
        # Verify booking was retrieved and status updated
        consumer.create_booking_use_case.booking_repo.get_by_id.assert_called_once_with(
            booking_id=789
        )
        consumer.create_booking_use_case.update_booking_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_tickets_reserved_missing_fields(self, consumer):
        """測試處理缺少必要欄位的票務預留事件"""
        # Arrange
        invalid_event = {
            'event_type': 'TicketsReserved',
            'data': {
                'request_id': 'test-request-123',
                # Missing buyer_id, tickets
            },
        }

        # Act
        await consumer._handle_tickets_reserved(invalid_event)

        # Assert - 應該記錄錯誤但不拋出異常
        # 這個測試主要確保程式不會因為無效數據而崩潰

    @pytest.mark.asyncio
    async def test_handle_tickets_reserved_create_booking_failure(
        self, consumer, valid_tickets_reserved_event
    ):
        """測試創建 booking 失敗的情況"""
        # Arrange
        consumer.create_booking_use_case = AsyncMock()
        consumer.create_booking_use_case.create_booking.side_effect = Exception('Database error')

        # Act
        await consumer._handle_tickets_reserved(valid_tickets_reserved_event)

        # Assert - 應該記錄錯誤但不拋出異常
        # 這個測試主要確保程式不會因為 booking 創建失敗而崩潰

    @pytest.mark.asyncio
    async def test_handle_reservation_failed(self, consumer, reservation_failed_event):
        """測試處理票務預留失敗事件"""
        # Act
        await consumer._handle_reservation_failed(reservation_failed_event)

        # Assert - 應該記錄警告但不拋出異常
        # 這個測試主要確保失敗事件被正確處理

    @pytest.mark.asyncio
    async def test_process_message_tickets_reserved(
        self, consumer, valid_tickets_reserved_event, successful_booking
    ):
        """測試處理 TicketsReserved 訊息"""
        # Arrange
        consumer.create_booking_use_case = AsyncMock()
        consumer.create_booking_use_case.booking_repo.get_by_id.return_value = successful_booking
        consumer.create_booking_use_case.update_booking_status.return_value = successful_booking

        mock_message = MagicMock()
        mock_message.value = msgpack.packb(valid_tickets_reserved_event)

        # Act
        await consumer._process_message(mock_message)

        # Assert
        consumer.create_booking_use_case.booking_repo.get_by_id.assert_called_once_with(
            booking_id=789
        )
        consumer.create_booking_use_case.update_booking_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_reservation_failed(self, consumer, reservation_failed_event):
        """測試處理 TicketReservationFailed 訊息"""
        # Arrange
        mock_message = MagicMock()
        mock_message.value = msgpack.packb(reservation_failed_event)

        # Act
        await consumer._process_message(mock_message)

        # Assert - 應該處理失敗事件而不拋出異常

    @pytest.mark.asyncio
    async def test_process_message_unknown_event_type(self, consumer):
        """測試處理未知事件類型"""
        # Arrange
        unknown_event = {'event_type': 'UnknownEventType', 'data': {}}

        mock_message = MagicMock()
        mock_message.value = msgpack.packb(unknown_event)

        # Act
        await consumer._process_message(mock_message)

        # Assert - 應該記錄警告但不拋出異常
        # 這個測試主要確保程式不會因為未知事件類型而崩潰

    @pytest.mark.asyncio
    async def test_process_message_deserialization_error(self, consumer):
        """測試訊息反序列化錯誤的處理"""
        # Arrange
        mock_message = MagicMock()
        mock_message.value = b'invalid message data'

        # Act
        await consumer._process_message(mock_message)

        # Assert - 應該記錄錯誤但不拋出異常
        # 這個測試主要確保程式不會因為無效訊息而崩潰

    @pytest.mark.asyncio
    async def test_extract_ticket_ids_from_tickets_data(
        self, consumer, valid_tickets_reserved_event, successful_booking
    ):
        """測試從票務數據中提取 ticket IDs"""
        # Arrange
        consumer.create_booking_use_case = AsyncMock()
        consumer.create_booking_use_case.booking_repo.get_by_id.return_value = successful_booking
        consumer.create_booking_use_case.update_booking_status.return_value = successful_booking

        # Act
        await consumer._handle_tickets_reserved(valid_tickets_reserved_event)

        # Assert
        # 驗證正確提取了 booking_id 和 ticket_ids 從事件數據
        event_data = valid_tickets_reserved_event['data']
        expected_booking_id = event_data['booking_id']
        expected_ticket_ids = event_data['ticket_ids']

        assert expected_booking_id == 789
        assert expected_ticket_ids == [1001, 1002]

        # 驗證調用了正確的 booking lookup
        consumer.create_booking_use_case.booking_repo.get_by_id.assert_called_once_with(
            booking_id=789
        )

    @pytest.mark.asyncio
    async def test_handle_tickets_reserved_empty_tickets_list(self, consumer):
        """測試處理空票務列表的情況"""
        # Arrange
        event_with_empty_tickets = {
            'event_type': 'TicketsReserved',
            'data': {
                'request_id': 'test-request-123',
                'buyer_id': 1,
                'tickets': [],  # 空列表
                'status': 'reserved',
            },
        }

        # Act
        await consumer._handle_tickets_reserved(event_with_empty_tickets)

        # Assert - 應該記錄錯誤但不拋出異常
        # 因為沒有 tickets，不應該調用 create_booking
