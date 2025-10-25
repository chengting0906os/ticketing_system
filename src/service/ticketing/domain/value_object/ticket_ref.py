from datetime import datetime
from typing import Optional
from uuid import UUID

import attrs

from src.service.ticketing.domain.enum.ticket_status import TicketStatus


@attrs.define
class TicketRef:
    event_id: UUID
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: TicketStatus
    # booking_id removed - now stored in Booking.ticket_ids
    buyer_id: Optional[UUID] = None
    id: Optional[UUID] = (
        None  # Only None when creating new ticket, always has value after persistence
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None
