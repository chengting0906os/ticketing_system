from typing import List

from pydantic import BaseModel


class SeatResponse(BaseModel):
    """
    Seat Response Schema (queried from Kvrocks, without ticket_id)
    """

    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str
    seat_identifier: str


class SectionStatsResponse(BaseModel):
    """Section Statistics Response"""

    section_id: str
    total: int
    available: int
    reserved: int
    sold: int
    event_id: int
    section: str
    subsection: int
    tickets: List[SeatResponse] = []
    total_count: int = 0


class ListSeatsBySectionResponse(BaseModel):
    seats: List[SeatResponse]
    total_count: int
    event_id: int
    section: str
    subsection: int | None = None
