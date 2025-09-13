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


class ReserveTicketsRequest(BaseModel):
    """Request to reserve tickets."""

    ticket_count: int = Field(..., gt=0, description='Number of tickets to reserve')


class TicketReservationDetail(BaseModel):
    """Details of a reserved ticket."""

    id: int
    seat_identifier: str
    price: int


class ReserveTicketsResponse(BaseModel):
    """Response after reserving tickets."""

    reservation_id: int
    buyer_id: int
    ticket_count: int
    status: str
    tickets: List[TicketReservationDetail]


class CancelReservationResponse(BaseModel):
    """Response after canceling a reservation."""

    reservation_id: int
    status: str
    cancelled_tickets: int
