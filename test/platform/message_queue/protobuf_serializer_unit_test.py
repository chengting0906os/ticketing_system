"""
Unit tests for Protobuf Serializer

Tests bidirectional conversion:
- Domain Event (attrs) -> Protobuf bytes
- Protobuf bytes -> Dict
"""

from datetime import datetime, timezone
from enum import Enum

from google.protobuf.json_format import MessageToDict
import pytest
import uuid_utils

from src.platform.message_queue.proto import domain_event_pb2 as pb
from src.platform.message_queue.protobuf_serializer import (
    _to_proto_value,
    convert_domain_event_to_proto,
    get_proto_class_by_event_type,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
    BookingCreatedDomainEvent,
)
from src.service.ticketing.domain.entity.booking_entity import BookingStatus


def deserialize_domain_event(*, data: bytes, event_type: str) -> dict:
    """Deserialize protobuf bytes to dict using MessageToDict"""
    proto_class = get_proto_class_by_event_type(event_type)
    proto_msg = proto_class()
    proto_msg.ParseFromString(data)
    return MessageToDict(proto_msg, preserving_proto_field_name=True)


@pytest.mark.unit
class TestValueConverters:
    def test_uuid_converts_to_string(self) -> None:
        uuid = uuid_utils.uuid7()
        result = _to_proto_value(uuid)
        assert result == str(uuid)
        assert isinstance(result, str)

    def test_datetime_converts_to_timestamp_ms(self) -> None:
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _to_proto_value(dt)
        expected = int(dt.timestamp() * 1000)
        assert result == expected

    def test_enum_converts_to_value(self) -> None:
        class TestEnum(Enum):
            ACTIVE = 'active'
            INACTIVE = 'inactive'

        result = _to_proto_value(TestEnum.ACTIVE)
        assert result == 'active'

    def test_passthrough_for_primitives(self) -> None:
        assert _to_proto_value('hello') == 'hello'
        assert _to_proto_value(123) == 123
        assert _to_proto_value(45.67) == 45.67
        assert _to_proto_value(True) is True


@pytest.mark.unit
class TestGetProtoClass:
    def test_returns_correct_proto_class(self) -> None:
        assert (
            get_proto_class_by_event_type('BookingCreatedDomainEvent')
            == pb.BookingCreatedDomainEvent
        )
        assert get_proto_class_by_event_type('BookingCancelledEvent') == pb.BookingCancelledEvent

    def test_raises_for_unknown_event_type(self) -> None:
        """Should raise ValueError for unknown event types"""
        with pytest.raises(ValueError, match='Unknown event type'):
            get_proto_class_by_event_type('UnknownEvent')


@pytest.mark.unit
class TestBookingCreatedEventSerialization:
    @pytest.fixture
    def booking_created_event(self) -> BookingCreatedDomainEvent:
        return BookingCreatedDomainEvent(
            booking_id=uuid_utils.uuid7(),
            buyer_id=42,
            event_id=1,
            total_price=5000,
            section='A',
            subsection=1,
            quantity=2,
            seat_selection_mode='manual',
            seat_positions=['1-1', '1-2'],
            status=BookingStatus.PROCESSING,
        )

    def test_serialize_and_deserialize_roundtrip(
        self, booking_created_event: BookingCreatedDomainEvent
    ) -> None:
        # Serialize
        data = convert_domain_event_to_proto(booking_created_event).SerializeToString()
        assert isinstance(data, bytes)

        # Deserialize
        result = deserialize_domain_event(data=data, event_type='BookingCreatedDomainEvent')

        # Verify fields
        assert result['booking_id'] == str(booking_created_event.booking_id)
        assert result['buyer_id'] == booking_created_event.buyer_id
        assert result['event_id'] == booking_created_event.event_id
        assert result['total_price'] == booking_created_event.total_price
        assert result['section'] == booking_created_event.section
        assert result['subsection'] == booking_created_event.subsection
        assert result['quantity'] == booking_created_event.quantity
        assert result['seat_selection_mode'] == booking_created_event.seat_selection_mode
        assert result['seat_positions'] == booking_created_event.seat_positions
        assert result['status'] == booking_created_event.status.value
        assert result['message_type'] == 'BookingCreatedDomainEvent'


@pytest.mark.unit
class TestBookingCancelledEventSerialization:
    """Test minimal BookingCancelledEvent (only booking_id, event_id, section, subsection)."""

    def test_serialize_and_deserialize_roundtrip(self) -> None:
        event = BookingCancelledEvent(
            booking_id=uuid_utils.uuid7(),
            event_id=1,
            section='A',
            subsection=1,
        )

        data = convert_domain_event_to_proto(event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='BookingCancelledEvent')

        assert result['booking_id'] == str(event.booking_id)
        assert result['event_id'] == 1
        assert result['section'] == 'A'
        assert result['subsection'] == 1
        assert result['message_type'] == 'BookingCancelledEvent'
