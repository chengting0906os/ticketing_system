from typing import List

from pydantic import BaseModel


class SeatResponse(BaseModel):
    id: int
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str
    seat_identifier: str


class ListSeatsBySectionResponse(BaseModel):
    seats: List[SeatResponse]
    total_count: int
    event_id: int
    section: str
    subsection: int | None = None
