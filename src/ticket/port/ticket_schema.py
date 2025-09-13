"""Ticket schemas."""

from typing import List
from pydantic import BaseModel, Field


class CreateTicketsRequest(BaseModel):
    """Request to create tickets for an event."""

    price: int = Field(..., gt=0, description='Ticket price in cents')


class CreateTicketsResponse(BaseModel):
    """Response after creating tickets."""

    tickets_created: int
    event_id: int
    message: str


class TicketResponse(BaseModel):
    """Individual ticket response."""

    id: int
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str
    seat_identifier: str


class ListTicketsResponse(BaseModel):
    """Response for listing tickets."""

    tickets: List[TicketResponse]
    total_count: int
    event_id: int


class ListTicketsBySectionResponse(BaseModel):
    """Response for listing tickets by section."""

    tickets: List[TicketResponse]
    total_count: int
    event_id: int
    section: str
    subsection: int | None = None
