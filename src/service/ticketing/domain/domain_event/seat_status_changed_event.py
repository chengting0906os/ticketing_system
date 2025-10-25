"""
Seat Status Changed Event

Published when seat availability changes (reserve/release/finalize).
Used by ticketing service to update its availability cache.
"""

from datetime import datetime
from uuid import UUID

import attrs


@attrs.define
class SeatStatusChangedEvent:
    """
    Event published when seat status changes in Kvrocks

    This event enables ticketing service to maintain an eventually-consistent
    cache of seat availability without polling Kvrocks.
    """

    event_id: UUID
    section: str
    subsection: int
    available: int
    reserved: int
    sold: int
    total: int
    occurred_at: datetime

    @property
    def aggregate_id(self) -> UUID:
        """Event ID serves as aggregate ID"""
        return self.event_id

    @property
    def section_id(self) -> str:
        """Formatted section ID"""
        return f'{self.section}-{self.subsection}'
