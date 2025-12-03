from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SubsectionConfig(_message.Message):
    __slots__ = ('rows', 'cols', 'price')
    ROWS_FIELD_NUMBER: _ClassVar[int]
    COLS_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    rows: int
    cols: int
    price: int
    def __init__(
        self, rows: _Optional[int] = ..., cols: _Optional[int] = ..., price: _Optional[int] = ...
    ) -> None: ...

class BookingCreatedDomainEvent(_message.Message):
    __slots__ = (
        'booking_id',
        'buyer_id',
        'event_id',
        'total_price',
        'section',
        'subsection',
        'quantity',
        'seat_selection_mode',
        'seat_positions',
        'status',
        'occurred_at',
        'config',
        'traceparent',
        'tracestate',
    )
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    SECTION_FIELD_NUMBER: _ClassVar[int]
    SUBSECTION_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    SEAT_SELECTION_MODE_FIELD_NUMBER: _ClassVar[int]
    SEAT_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    TRACEPARENT_FIELD_NUMBER: _ClassVar[int]
    TRACESTATE_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: int
    event_id: int
    total_price: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: _containers.RepeatedScalarFieldContainer[str]
    status: str
    occurred_at: int
    config: SubsectionConfig
    traceparent: str
    tracestate: str
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[int] = ...,
        event_id: _Optional[int] = ...,
        total_price: _Optional[int] = ...,
        section: _Optional[str] = ...,
        subsection: _Optional[int] = ...,
        quantity: _Optional[int] = ...,
        seat_selection_mode: _Optional[str] = ...,
        seat_positions: _Optional[_Iterable[str]] = ...,
        status: _Optional[str] = ...,
        occurred_at: _Optional[int] = ...,
        config: _Optional[_Union[SubsectionConfig, _Mapping]] = ...,
        traceparent: _Optional[str] = ...,
        tracestate: _Optional[str] = ...,
    ) -> None: ...

class SeatsReservedEvent(_message.Message):
    __slots__ = (
        'booking_id',
        'buyer_id',
        'event_id',
        'section',
        'subsection',
        'seat_selection_mode',
        'reserved_seats',
        'total_price',
        'subsection_stats',
        'event_stats',
        'status',
        'occurred_at',
        'traceparent',
        'tracestate',
    )
    class SubsectionStatsEntry(_message.Message):
        __slots__ = ('key', 'value')
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...

    class EventStatsEntry(_message.Message):
        __slots__ = ('key', 'value')
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...

    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    SECTION_FIELD_NUMBER: _ClassVar[int]
    SUBSECTION_FIELD_NUMBER: _ClassVar[int]
    SEAT_SELECTION_MODE_FIELD_NUMBER: _ClassVar[int]
    RESERVED_SEATS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    SUBSECTION_STATS_FIELD_NUMBER: _ClassVar[int]
    EVENT_STATS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    TRACEPARENT_FIELD_NUMBER: _ClassVar[int]
    TRACESTATE_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    seat_selection_mode: str
    reserved_seats: _containers.RepeatedScalarFieldContainer[str]
    total_price: int
    subsection_stats: _containers.ScalarMap[str, int]
    event_stats: _containers.ScalarMap[str, int]
    status: str
    occurred_at: int
    traceparent: str
    tracestate: str
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[int] = ...,
        event_id: _Optional[int] = ...,
        section: _Optional[str] = ...,
        subsection: _Optional[int] = ...,
        seat_selection_mode: _Optional[str] = ...,
        reserved_seats: _Optional[_Iterable[str]] = ...,
        total_price: _Optional[int] = ...,
        subsection_stats: _Optional[_Mapping[str, int]] = ...,
        event_stats: _Optional[_Mapping[str, int]] = ...,
        status: _Optional[str] = ...,
        occurred_at: _Optional[int] = ...,
        traceparent: _Optional[str] = ...,
        tracestate: _Optional[str] = ...,
    ) -> None: ...

class SeatReservationFailedEvent(_message.Message):
    __slots__ = (
        'booking_id',
        'buyer_id',
        'event_id',
        'section',
        'subsection',
        'quantity',
        'seat_selection_mode',
        'seat_positions',
        'error_message',
        'status',
        'occurred_at',
        'traceparent',
        'tracestate',
    )
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    SECTION_FIELD_NUMBER: _ClassVar[int]
    SUBSECTION_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    SEAT_SELECTION_MODE_FIELD_NUMBER: _ClassVar[int]
    SEAT_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    TRACEPARENT_FIELD_NUMBER: _ClassVar[int]
    TRACESTATE_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: _containers.RepeatedScalarFieldContainer[str]
    error_message: str
    status: str
    occurred_at: int
    traceparent: str
    tracestate: str
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[int] = ...,
        event_id: _Optional[int] = ...,
        section: _Optional[str] = ...,
        subsection: _Optional[int] = ...,
        quantity: _Optional[int] = ...,
        seat_selection_mode: _Optional[str] = ...,
        seat_positions: _Optional[_Iterable[str]] = ...,
        error_message: _Optional[str] = ...,
        status: _Optional[str] = ...,
        occurred_at: _Optional[int] = ...,
        traceparent: _Optional[str] = ...,
        tracestate: _Optional[str] = ...,
    ) -> None: ...

class BookingPaidEvent(_message.Message):
    __slots__ = (
        'booking_id',
        'buyer_id',
        'event_id',
        'ticket_ids',
        'seat_positions',
        'paid_at',
        'total_amount',
        'traceparent',
        'tracestate',
    )
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TICKET_IDS_FIELD_NUMBER: _ClassVar[int]
    SEAT_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    PAID_AT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    TRACEPARENT_FIELD_NUMBER: _ClassVar[int]
    TRACESTATE_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: int
    event_id: int
    ticket_ids: _containers.RepeatedScalarFieldContainer[int]
    seat_positions: _containers.RepeatedScalarFieldContainer[str]
    paid_at: int
    total_amount: float
    traceparent: str
    tracestate: str
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[int] = ...,
        event_id: _Optional[int] = ...,
        ticket_ids: _Optional[_Iterable[int]] = ...,
        seat_positions: _Optional[_Iterable[str]] = ...,
        paid_at: _Optional[int] = ...,
        total_amount: _Optional[float] = ...,
        traceparent: _Optional[str] = ...,
        tracestate: _Optional[str] = ...,
    ) -> None: ...

class BookingCancelledEvent(_message.Message):
    __slots__ = (
        'booking_id',
        'buyer_id',
        'event_id',
        'ticket_ids',
        'seat_positions',
        'cancelled_at',
        'traceparent',
        'tracestate',
    )
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TICKET_IDS_FIELD_NUMBER: _ClassVar[int]
    SEAT_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    CANCELLED_AT_FIELD_NUMBER: _ClassVar[int]
    TRACEPARENT_FIELD_NUMBER: _ClassVar[int]
    TRACESTATE_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: int
    event_id: int
    ticket_ids: _containers.RepeatedScalarFieldContainer[int]
    seat_positions: _containers.RepeatedScalarFieldContainer[str]
    cancelled_at: int
    traceparent: str
    tracestate: str
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[int] = ...,
        event_id: _Optional[int] = ...,
        ticket_ids: _Optional[_Iterable[int]] = ...,
        seat_positions: _Optional[_Iterable[str]] = ...,
        cancelled_at: _Optional[int] = ...,
        traceparent: _Optional[str] = ...,
        tracestate: _Optional[str] = ...,
    ) -> None: ...
