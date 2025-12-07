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
from src.service.reservation.driven_adapter.reservation_mq_publisher import (
    SeatReservationFailedEvent,
    SeatsReservedEvent,
)
from src.service.shared_kernel.domain.value_object import SubsectionConfig
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
    BookingCreatedDomainEvent,
    BookingPaidEvent,
)
from src.service.ticketing.domain.entity.booking_entity import BookingStatus


def deserialize_domain_event(*, data: bytes, event_type: str) -> dict:
    """Deserialize using MessageToDict (same as Quix ProtobufDeserializer internally)"""
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
        assert get_proto_class_by_event_type('SeatsReservedEvent') == pb.SeatsReservedEvent
        assert (
            get_proto_class_by_event_type('SeatReservationFailedEvent')
            == pb.SeatReservationFailedEvent
        )
        assert get_proto_class_by_event_type('BookingPaidEvent') == pb.BookingPaidEvent
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
            seat_positions=['A1-1-1', 'A1-1-2'],
            status=BookingStatus.PROCESSING,
            occurred_at=datetime.now(timezone.utc),
            config=SubsectionConfig(rows=10, cols=20, price=2500),
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

    def test_config_field_serialization(
        self, booking_created_event: BookingCreatedDomainEvent
    ) -> None:
        proto_msg = convert_domain_event_to_proto(booking_created_event)

        assert proto_msg.config.rows == 10
        assert proto_msg.config.cols == 20
        assert proto_msg.config.price == 2500

    def test_config_deserialization_to_dict(
        self, booking_created_event: BookingCreatedDomainEvent
    ) -> None:
        """SubsectionConfig should deserialize to dict"""
        data = convert_domain_event_to_proto(booking_created_event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='BookingCreatedDomainEvent')

        assert result['config'] == {'rows': 10, 'cols': 20, 'price': 2500}

    def test_config_with_zero_price(self) -> None:
        """Config with price=0 (free tickets) should serialize correctly"""
        event = BookingCreatedDomainEvent(
            booking_id=uuid_utils.uuid7(),
            buyer_id=42,
            event_id=1,
            total_price=0,
            section='A',
            subsection=1,
            quantity=2,
            seat_selection_mode='auto',
            seat_positions=[],
            status=BookingStatus.PROCESSING,
            occurred_at=datetime.now(timezone.utc),
            config=SubsectionConfig(rows=10, cols=20, price=0),
        )

        data = convert_domain_event_to_proto(event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='BookingCreatedDomainEvent')

        # With proto3 `optional` keyword, price=0 is now preserved (not omitted)
        assert result['config'] == {'rows': 10, 'cols': 20, 'price': 0}

    def test_config_none_omitted_from_proto(self) -> None:
        """config=None should be omitted entirely (not included in proto)"""
        event = BookingCreatedDomainEvent(
            booking_id=uuid_utils.uuid7(),
            buyer_id=42,
            event_id=1,
            total_price=0,
            section='A',
            subsection=1,
            quantity=2,
            seat_selection_mode='auto',
            seat_positions=[],
            status=BookingStatus.PROCESSING,
            occurred_at=datetime.now(timezone.utc),
            config=None,  # Explicitly None
        )

        data = convert_domain_event_to_proto(event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='BookingCreatedDomainEvent')

        # config=None means field not set, so MessageToDict won't include it
        assert 'config' not in result


@pytest.mark.unit
class TestSeatsReservedEventSerialization:
    @pytest.fixture
    def seats_reserved_event(self) -> SeatsReservedEvent:
        return SeatsReservedEvent(
            booking_id='booking-123',
            buyer_id=42,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A1-1-1', 'A1-1-2'],
            total_price=5000,
            subsection_stats={'available': 98, 'reserved': 2, 'sold': 0, 'total': 100},
            event_stats={'available': 49998, 'reserved': 2, 'sold': 0, 'total': 50000},
        )

    def test_serialize_and_deserialize_roundtrip(
        self, seats_reserved_event: SeatsReservedEvent
    ) -> None:
        data = convert_domain_event_to_proto(seats_reserved_event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='SeatsReservedEvent')

        assert result['booking_id'] == seats_reserved_event.booking_id
        assert result['buyer_id'] == seats_reserved_event.buyer_id
        assert result['reserved_seats'] == seats_reserved_event.reserved_seats
        assert result['subsection_stats'] == seats_reserved_event.subsection_stats
        assert result['event_stats'] == seats_reserved_event.event_stats


@pytest.mark.unit
class TestSeatReservationFailedEventSerialization:
    def test_serialize_and_deserialize_roundtrip(self) -> None:
        event = SeatReservationFailedEvent(
            booking_id='booking-456',
            buyer_id=42,
            event_id=1,
            section='B',
            subsection=2,
            quantity=3,
            seat_selection_mode='auto',
            seat_positions=[],
            error_message='Insufficient seats available',
        )

        data = convert_domain_event_to_proto(event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='SeatReservationFailedEvent')

        assert result['booking_id'] == event.booking_id
        assert result['error_message'] == event.error_message
        assert result['status'] == 'reservation_failed'


@pytest.mark.unit
class TestBookingPaidEventSerialization:
    def test_serialize_and_deserialize_roundtrip(self) -> None:
        paid_at = datetime.now(timezone.utc)
        event = BookingPaidEvent(
            booking_id=uuid_utils.uuid7(),
            buyer_id=42,
            event_id=1,
            section='A',
            subsection=1,
            ticket_ids=[101, 102, 103],
            paid_at=paid_at,
            total_amount=7500.0,
        )

        data = convert_domain_event_to_proto(event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='BookingPaidEvent')

        assert result['booking_id'] == str(event.booking_id)
        assert result['ticket_ids'] == [101, 102, 103]
        assert result['total_amount'] == 7500.0


@pytest.mark.unit
class TestBookingCancelledEventSerialization:
    def test_serialize_and_deserialize_roundtrip(self) -> None:
        cancelled_at = datetime.now(timezone.utc)
        event = BookingCancelledEvent(
            booking_id=uuid_utils.uuid7(),
            buyer_id=42,
            event_id=1,
            section='A',
            subsection=1,
            ticket_ids=[101, 102],
            seat_positions=['A1-1-1', 'A1-1-2'],
            cancelled_at=cancelled_at,
        )

        data = convert_domain_event_to_proto(event).SerializeToString()
        result = deserialize_domain_event(data=data, event_type='BookingCancelledEvent')

        assert result['booking_id'] == str(event.booking_id)
        assert result['ticket_ids'] == [101, 102]
        assert result['seat_positions'] == ['A1-1-1', 'A1-1-2']
