from fastapi import APIRouter, Depends, status

from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import (
    require_buyer,
    require_buyer_or_seller,
    require_seller,
)
from src.ticket.port.ticket_schema import (
    CancelReservationResponse,
    CreateTicketsRequest,
    CreateTicketsResponse,
    ListTicketsBySectionResponse,
    ListTicketsResponse,
    ReserveTicketsRequest,
    ReserveTicketsResponse,
    TicketResponse,
)
from src.ticket.use_case.cancel_reservation_use_case import CancelReservationUseCase
from src.ticket.use_case.create_tickets_use_case import CreateTicketsUseCase
from src.ticket.use_case.list_tickets_use_case import ListTicketsUseCase
from src.ticket.use_case.reserve_tickets_use_case import ReserveTicketsUseCase
from src.user.domain.user_model import User


router = APIRouter(prefix='/events', tags=['tickets'])
ticket_router = APIRouter(prefix='/ticket', tags=['ticket-operations'])


@router.post('/{event_id}/tickets', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_tickets_for_event(
    event_id: int,
    request: CreateTicketsRequest,
    current_user: User = Depends(require_seller),
    use_case: CreateTicketsUseCase = Depends(CreateTicketsUseCase.depends),
) -> CreateTicketsResponse:
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


@router.post('/{event_id}/reserve', status_code=status.HTTP_200_OK)
@Logger.io
async def reserve_tickets_for_event(
    event_id: int,
    request: ReserveTicketsRequest,
    current_user: User = Depends(require_buyer),
    use_case: ReserveTicketsUseCase = Depends(ReserveTicketsUseCase.depends),
) -> ReserveTicketsResponse:
    reservation_data = await use_case.reserve_tickets(
        event_id=event_id,
        ticket_count=request.ticket_count,
        buyer_id=current_user.id,
    )

    return ReserveTicketsResponse(**reservation_data)


@ticket_router.delete('/reservations/{reservation_id}', status_code=status.HTTP_200_OK)
@Logger.io
async def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(require_buyer),
    use_case: CancelReservationUseCase = Depends(CancelReservationUseCase.depends),
) -> CancelReservationResponse:
    result = await use_case.cancel_reservation(
        reservation_id=reservation_id,
        buyer_id=current_user.id,
    )

    return CancelReservationResponse(**result)


@ticket_router.post('/cleanup-expired-reservations', status_code=status.HTTP_200_OK)
@Logger.io
async def cleanup_expired_reservations():
    """System endpoint to cleanup expired reservations."""
    from datetime import datetime, timedelta

    from sqlalchemy import text

    from src.shared.config.db_setting import async_session_maker
    from src.shared.service.unit_of_work import SqlAlchemyUnitOfWork

    # Find tickets reserved more than 15 minutes ago
    cutoff_time = datetime.now() - timedelta(minutes=15)

    # Get all expired reserved tickets
    ticket_ids = []
    async with async_session_maker() as session:
        uow = SqlAlchemyUnitOfWork(session)
        async with uow:
            # This is a simplified implementation - in production you'd have a proper use case
            result = await uow.session.execute(
                text("""
                SELECT id FROM ticket
                WHERE status = 'reserved'
                AND reserved_at < :cutoff_time
                """),
                {'cutoff_time': cutoff_time},
            )
            ticket_ids = [row[0] for row in result.fetchall()]

            if ticket_ids:
                # Update expired tickets back to available
                await uow.session.execute(
                    text("""
                    UPDATE ticket
                    SET status = 'available', buyer_id = NULL, reserved_at = NULL
                    WHERE id = ANY(:ticket_ids)
                    """),
                    {'ticket_ids': ticket_ids},
                )
            await uow.commit()

    return {
        'message': f'Cleaned up {len(ticket_ids)} expired reservations',
        'count': len(ticket_ids),
    }
