from datetime import datetime
from typing import Optional

import attrs

from src.service.ticketing.domain.enum.ticket_status import TicketStatus


@attrs.define
class TicketEntity:
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: TicketStatus
    buyer_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None
