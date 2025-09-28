# Type stub for domain_event_pb2.py
# This helps Pylance understand the dynamically generated Protobuf classes

from typing import Any, Optional

from google.protobuf.message import Message

class DomainEvent(Message):
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    occurred_at: int
    data: bytes

    def __init__(
        self,
        event_id: Optional[str] = ...,
        event_type: Optional[str] = ...,
        aggregate_id: Optional[str] = ...,
        aggregate_type: Optional[str] = ...,
        occurred_at: Optional[int] = ...,
        data: Optional[bytes] = ...,
    ) -> None: ...

class TicketsReservedEvent(Message):
    buyer_id: str
    booking_id: str
    ticket_ids: list[str]
    event_id: str
    quantity: int
    total_price: float

    def __init__(
        self,
        buyer_id: Optional[str] = ...,
        booking_id: Optional[str] = ...,
        ticket_ids: Optional[list[str]] = ...,
        event_id: Optional[str] = ...,
        quantity: Optional[int] = ...,
        total_price: Optional[float] = ...,
    ) -> None: ...

class TicketReservationFailedEvent(Message):
    request_id: str
    buyer_id: str
    event_id: str
    error_code: str
    error_message: str
    requested_quantity: int

    def __init__(
        self,
        request_id: Optional[str] = ...,
        buyer_id: Optional[str] = ...,
        event_id: Optional[str] = ...,
        error_code: Optional[str] = ...,
        error_message: Optional[str] = ...,
        requested_quantity: Optional[int] = ...,
    ) -> None: ...

class BookingPaidEvent(Message):
    booking_id: str
    buyer_id: str
    payment_id: str
    amount: float
    currency: str
    paid_at: int

    def __init__(
        self,
        booking_id: Optional[str] = ...,
        buyer_id: Optional[str] = ...,
        payment_id: Optional[str] = ...,
        amount: Optional[float] = ...,
        currency: Optional[str] = ...,
        paid_at: Optional[int] = ...,
    ) -> None: ...

class BookingCancelledEvent(Message):
    booking_id: str
    buyer_id: str
    reason: str
    cancelled_at: int
    refunded_ticket_ids: list[str]

    def __init__(
        self,
        booking_id: Optional[str] = ...,
        buyer_id: Optional[str] = ...,
        reason: Optional[str] = ...,
        cancelled_at: Optional[int] = ...,
        refunded_ticket_ids: Optional[list[str]] = ...,
    ) -> None: ...

DESCRIPTOR: Any
