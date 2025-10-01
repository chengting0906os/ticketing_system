from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MqDomainEvent(_message.Message):
    __slots__ = (
        'event_id',
        'event_type',
        'aggregate_id',
        'aggregate_type',
        'occurred_at',
        'metadata',
        'data',
    )
    class MetadataEntry(_message.Message):
        __slots__ = ('key', 'value')
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_ID_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_TYPE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    occurred_at: int
    metadata: _containers.ScalarMap[str, str]
    data: bytes
    def __init__(
        self,
        event_id: _Optional[str] = ...,
        event_type: _Optional[str] = ...,
        aggregate_id: _Optional[str] = ...,
        aggregate_type: _Optional[str] = ...,
        occurred_at: _Optional[int] = ...,
        metadata: _Optional[_Mapping[str, str]] = ...,
        data: _Optional[bytes] = ...,
    ) -> None: ...

class TicketsReservedEvent(_message.Message):
    __slots__ = ('buyer_id', 'booking_id', 'ticket_ids', 'event_id', 'quantity', 'total_price')
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    TICKET_IDS_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    buyer_id: str
    booking_id: str
    ticket_ids: _containers.RepeatedScalarFieldContainer[str]
    event_id: str
    quantity: int
    total_price: float
    def __init__(
        self,
        buyer_id: _Optional[str] = ...,
        booking_id: _Optional[str] = ...,
        ticket_ids: _Optional[_Iterable[str]] = ...,
        event_id: _Optional[str] = ...,
        quantity: _Optional[int] = ...,
        total_price: _Optional[float] = ...,
    ) -> None: ...

class TicketReservationFailedEvent(_message.Message):
    __slots__ = (
        'request_id',
        'buyer_id',
        'event_id',
        'error_code',
        'error_message',
        'requested_quantity',
    )
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    REQUESTED_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    buyer_id: str
    event_id: str
    error_code: str
    error_message: str
    requested_quantity: int
    def __init__(
        self,
        request_id: _Optional[str] = ...,
        buyer_id: _Optional[str] = ...,
        event_id: _Optional[str] = ...,
        error_code: _Optional[str] = ...,
        error_message: _Optional[str] = ...,
        requested_quantity: _Optional[int] = ...,
    ) -> None: ...

class BookingPaidEvent(_message.Message):
    __slots__ = ('booking_id', 'buyer_id', 'payment_id', 'amount', 'currency', 'paid_at')
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    PAID_AT_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: str
    payment_id: str
    amount: float
    currency: str
    paid_at: int
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[str] = ...,
        payment_id: _Optional[str] = ...,
        amount: _Optional[float] = ...,
        currency: _Optional[str] = ...,
        paid_at: _Optional[int] = ...,
    ) -> None: ...

class BookingCancelledEvent(_message.Message):
    __slots__ = ('booking_id', 'buyer_id', 'reason', 'cancelled_at', 'refunded_ticket_ids')
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    BUYER_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    CANCELLED_AT_FIELD_NUMBER: _ClassVar[int]
    REFUNDED_TICKET_IDS_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    buyer_id: str
    reason: str
    cancelled_at: int
    refunded_ticket_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        booking_id: _Optional[str] = ...,
        buyer_id: _Optional[str] = ...,
        reason: _Optional[str] = ...,
        cancelled_at: _Optional[int] = ...,
        refunded_ticket_ids: _Optional[_Iterable[str]] = ...,
    ) -> None: ...
