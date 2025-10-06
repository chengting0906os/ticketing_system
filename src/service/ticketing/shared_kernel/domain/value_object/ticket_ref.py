from datetime import datetime
from typing import Optional

import attrs

from src.service.ticketing.shared_kernel.domain.enum.ticket_status import TicketStatus


@attrs.define
class TicketRef:
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: TicketStatus
    # booking_id removed - now stored in Booking.ticket_ids
    buyer_id: Optional[int] = None
    id: Optional[int] = (
        None  # Only None when creating new ticket, always has value after persistence
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None
