from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import attrs

from src.shared.logging.loguru_io import Logger


class TicketStatus(Enum):
    AVAILABLE = 'available'
    RESERVED = 'reserved'
    SOLD = 'sold'


@attrs.define
class Ticket:
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: TicketStatus
    order_id: Optional[int] = None
    buyer_id: Optional[int] = None
    id: Optional[int] = (
        None  # Only None when creating new ticket, always has value after persistence
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None

    @Logger.io
    def __attrs_post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)

    @property
    @Logger.io
    def seat_identifier(self) -> str:
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    @Logger.io
    def reserve(self, *, buyer_id: int) -> None:
        if self.status != TicketStatus.AVAILABLE:
            raise ValueError(f'Cannot reserve ticket with status {self.status}')

        now = datetime.now(timezone.utc)
        self.status = TicketStatus.RESERVED
        self.buyer_id = buyer_id
        self.reserved_at = now
        self.updated_at = now

    @Logger.io
    def sell(self) -> None:
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot sell ticket with status {self.status}')

        self.status = TicketStatus.SOLD
        self.updated_at = datetime.now(timezone.utc)

    @Logger.io
    def release(self) -> None:
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot release ticket with status {self.status}')

        self.status = TicketStatus.AVAILABLE
        self.order_id = None
        self.buyer_id = None
        self.reserved_at = None
        self.updated_at = datetime.now(timezone.utc)

    @Logger.io
    def cancel_reservation(self, *, buyer_id: int) -> None:
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot cancel reservation for ticket with status {self.status}')

        if self.buyer_id != buyer_id:
            raise ValueError('Cannot cancel reservation that belongs to another buyer')

        self.release()
