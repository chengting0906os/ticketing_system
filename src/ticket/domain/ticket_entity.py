"""Ticket domain entity."""

from datetime import datetime
from enum import Enum
from typing import Optional

import attrs


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

    def __attrs_post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    @property
    def seat_identifier(self) -> str:
        """Generate unique seat identifier."""
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    def reserve(self, order_id: int, buyer_id: int) -> None:
        """Reserve ticket for an order."""
        if self.status != TicketStatus.AVAILABLE:
            raise ValueError(f'Cannot reserve ticket with status {self.status}')

        self.status = TicketStatus.RESERVED
        self.order_id = order_id
        self.buyer_id = buyer_id
        self.updated_at = datetime.now()

    def sell(self) -> None:
        """Mark ticket as sold."""
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot sell ticket with status {self.status}')

        self.status = TicketStatus.SOLD
        self.updated_at = datetime.now()

    def release(self) -> None:
        """Release ticket reservation back to available."""
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot release ticket with status {self.status}')

        self.status = TicketStatus.AVAILABLE
        self.order_id = None
        self.buyer_id = None
        self.updated_at = datetime.now()
