"""Ticket controller."""

from fastapi import APIRouter, Depends, status

from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import require_seller, require_buyer_or_seller
from src.ticket.port.ticket_schema import (
    CreateTicketsRequest,
    CreateTicketsResponse,
    ListTicketsBySectionResponse,
    ListTicketsResponse,
    TicketResponse,
)
from src.ticket.use_case.create_tickets_use_case import CreateTicketsUseCase
from src.ticket.use_case.list_tickets_use_case import ListTicketsUseCase
from src.user.domain.user_model import User


router = APIRouter(prefix='/events', tags=['tickets'])


@router.post('/{event_id}/tickets', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_tickets_for_event(
    event_id: int,
    request: CreateTicketsRequest,
    current_user: User = Depends(require_seller),
    use_case: CreateTicketsUseCase = Depends(CreateTicketsUseCase.depends),
) -> CreateTicketsResponse:
    """Create all tickets for an event (seller only)."""
    tickets = await use_case.create_all_tickets_for_event(
        event_id=event_id,
        price=request.price,
        seller_id=current_user.id,
    )

    return CreateTicketsResponse(
        tickets_created=len(tickets),
        event_id=event_id,
        message=f'Successfully created {len(tickets)} tickets',
    )


def _ticket_to_response(ticket) -> TicketResponse:
    """Convert ticket entity to response format."""
    return TicketResponse(
        id=ticket.id,
        event_id=ticket.event_id,
        section=ticket.section,
        subsection=ticket.subsection,
        row=ticket.row,
        seat=ticket.seat,
        price=ticket.price,
        status=ticket.status.value,
        seat_identifier=ticket.seat_identifier,
    )


@router.get('/{event_id}/tickets', status_code=status.HTTP_200_OK)
@Logger.io
async def list_tickets_by_event(
    event_id: int,
    current_user: User = Depends(require_buyer_or_seller),
    use_case: ListTicketsUseCase = Depends(ListTicketsUseCase.depends),
) -> ListTicketsResponse:
    """List tickets for an event. Sellers see all tickets, buyers see available only."""
    # Determine if user is a seller for this event
    seller_id = None
    if current_user.role == 'seller':
        seller_id = current_user.id

    tickets = await use_case.list_tickets_by_event(
        event_id=event_id,
        seller_id=seller_id,
    )

    ticket_responses = [_ticket_to_response(ticket) for ticket in tickets]

    return ListTicketsResponse(
        tickets=ticket_responses,
        total_count=len(ticket_responses),
        event_id=event_id,
    )


@router.get('/{event_id}/tickets/section/{section}', status_code=status.HTTP_200_OK)
@Logger.io
async def list_tickets_by_section(
    event_id: int,
    section: str,
    subsection: int | None = None,
    current_user: User = Depends(require_seller),
    use_case: ListTicketsUseCase = Depends(ListTicketsUseCase.depends),
) -> ListTicketsBySectionResponse:
    """List tickets for specific section/subsection of an event (seller only)."""
    tickets = await use_case.list_tickets_by_section(
        event_id=event_id,
        section=section,
        subsection=subsection,
        seller_id=current_user.id,
    )

    ticket_responses = [_ticket_to_response(ticket) for ticket in tickets]

    return ListTicketsBySectionResponse(
        tickets=ticket_responses,
        total_count=len(ticket_responses),
        event_id=event_id,
        section=section,
        subsection=subsection,
    )
