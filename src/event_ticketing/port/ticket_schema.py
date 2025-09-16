from typing import List

from pydantic import BaseModel, Field


class CreateTicketsRequest(BaseModel):
    price: int = Field(..., gt=0, description='Ticket price in cents')


class CreateTicketsResponse(BaseModel):
    tickets_created: int
    event_id: int
    message: str


class TicketResponse(BaseModel):
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
    tickets: List[TicketResponse]
    total_count: int
    event_id: int


class ListTicketsBySectionResponse(BaseModel):
    tickets: List[TicketResponse]
    total_count: int
    event_id: int
    section: str
    subsection: int | None = None


class ReserveTicketsRequest(BaseModel):
    ticket_count: int = Field(..., gt=0, description='Number of tickets to reserve')


class TicketReservationDetail(BaseModel):
    id: int
    seat_identifier: str
    price: int


class ReserveTicketsResponse(BaseModel):
    reservation_id: int
    buyer_id: int
    ticket_count: int
    status: str
    tickets: List[TicketReservationDetail]


class CancelReservationResponse(BaseModel):
    status: str
    cancelled_tickets: int
