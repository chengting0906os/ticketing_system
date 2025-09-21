from typing import List, Optional

from fastapi import APIRouter, Depends, Request, status
from sse_starlette.sse import EventSourceResponse

from src.event_ticketing.port.event_schema import (
    EventCreateRequest,
    EventResponse,
)
from src.event_ticketing.port.ticket_schema import (
    CreateTicketsRequest,
    CreateTicketsResponse,
    ListTicketsBySectionResponse,
    ListTicketsResponse,
    TicketResponse,
)
from src.event_ticketing.use_case.create_event_use_case import (
    CreateEventUseCase,
    GetEventUseCase,
    ListEventsUseCase,
)
from src.event_ticketing.use_case.create_tickets_use_case import CreateTicketsUseCase
from src.event_ticketing.use_case.get_availability_use_case import GetAvailabilityUseCase
from src.event_ticketing.use_case.list_tickets_use_case import ListTicketsUseCase
from src.event_ticketing.use_case.reserve_tickets_use_case import ReserveTicketsUseCase
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import (
    require_buyer,
    require_buyer_or_seller,
    require_seller,
)
from src.user.domain.user_entity import UserRole
from src.user.domain.user_model import User


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_event(
    request: EventCreateRequest,
    current_user: User = Depends(require_seller),
    use_case: CreateEventUseCase = Depends(CreateEventUseCase.depends),
) -> EventResponse:
    event = await use_case.create(
        name=request.name,
        description=request.description,
        seller_id=current_user.id,  # Use current user's ID
        venue_name=request.venue_name,
        seating_config=request.seating_config,
        is_active=request.is_active,
    )

    if event.id is None:
        raise ValueError('Event ID should not be None after creation.')

    return EventResponse(
        id=event.id,
        name=event.name,
        description=event.description,
        seller_id=event.seller_id,
        venue_name=event.venue_name,
        seating_config=event.seating_config,
        is_active=event.is_active,
        status=event.status.value,  # Convert enum to string
    )


@router.get('/{event_id}', status_code=status.HTTP_200_OK)
@Logger.io
async def get_event(
    event_id: int, use_case: GetEventUseCase = Depends(GetEventUseCase.depends)
) -> EventResponse:
    event = await use_case.get_by_id(event_id=event_id)

    if not event:
        raise NotFoundError(f'Event with id {event_id} not found')

    return EventResponse(
        id=event_id,
        name=event.name,
        description=event.description,
        seller_id=event.seller_id,
        venue_name=event.venue_name,
        seating_config=event.seating_config,
        is_active=event.is_active,
        status=event.status.value,
    )


@router.get('', status_code=status.HTTP_200_OK)
@Logger.io
async def list_events(
    seller_id: Optional[int] = None,
    use_case: ListEventsUseCase = Depends(ListEventsUseCase.depends),
) -> List[EventResponse]:
    if seller_id is not None:
        events = await use_case.get_by_seller(seller_id)
    else:
        events = await use_case.list_available()

    result = []
    for event in events:
        if event.id is not None:
            result.append(
                EventResponse(
                    id=event.id,
                    name=event.name,
                    description=event.description,
                    seller_id=event.seller_id,
                    venue_name=event.venue_name,
                    seating_config=event.seating_config,
                    is_active=event.is_active,
                    status=event.status.value,
                )
            )
    return result


# @router.get('/{event_id}/availability/section/{section}', status_code=status.HTTP_200_OK)
# @Logger.io
# async def get_section_availability(
#     event_id: int,
#     section: str,
#     subsection: Optional[int] = None,
#     use_case: GetAvailabilityUseCase = Depends(GetAvailabilityUseCase.depends),
# ) -> SectionAvailabilityResponse:
#     """Get ticket availability for a specific section or subsection (public endpoint)."""
#     return await use_case.get_section_availability(
#         event_id=event_id, section=section, subsection=subsection
#     )


# Ticket management endpoints for events


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


@router.post('/{event_id}/tickets', status_code=status.HTTP_201_CREATED)
@Logger.io(truncate_content=True)
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


@router.get('/{event_id}/tickets', status_code=status.HTTP_200_OK)
@Logger.io(truncate_content=True)
async def list_tickets_by_event(
    event_id: int,
    current_user: User = Depends(require_buyer_or_seller),
    use_case: ListTicketsUseCase = Depends(ListTicketsUseCase.depends),
) -> ListTicketsResponse:
    # Determine if user is a seller for this event
    seller_id = None
    if current_user.role == UserRole.SELLER:
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


@router.get('/sse/{event_id}/status')
@Logger.io(truncate_content=True)
async def sse_event_with_all_subsections_tickets_status(
    request: Request,
    event_id: int,
    current_user: User = Depends(require_buyer_or_seller),  # 使用 DI 驗證
    availability_use_case: GetAvailabilityUseCase = Depends(GetAvailabilityUseCase.depends),
):
    async def event_generator():
        yield {
            'event': 'connected',
            'data': {
                'message': 'SSE connection established',
                'event_id': event_id,
                'user_id': current_user.id,
            },
        }

        try:
            initial_status = (
                await availability_use_case.get_event_status_with_all_subsections_tickets_count(
                    event_id=event_id
                )
            )

            yield {
                'event': 'initial_status',
                'data': {
                    'event_id': event_id,
                    'price_groups': [
                        {
                            'price': pg.price,
                            'subsections': [
                                {
                                    'subsection': sub.subsection,
                                    'total_seats': sub.total_seats,
                                    'available_seats': sub.available_seats,
                                    'status': sub.status,
                                }
                                for sub in pg.subsections
                            ],
                        }
                        for pg in initial_status.price_groups
                    ],
                },
            }
        except Exception as e:
            yield {'event': 'error', 'data': {'message': f'Failed to get initial status: {str(e)}'}}

    return EventSourceResponse(
        event_generator(),
        headers={
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control',
        },
        ping=30,
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


# Ticket reservation endpoints (moved from ticket module)


@router.post('/{event_id}/reserve', status_code=status.HTTP_200_OK)
@Logger.io
async def reserve_tickets_for_event(
    event_id: int,
    request: dict,  # Expecting {'ticket_count': int, 'section': str (optional), 'subsection': int (optional)}
    current_user: User = Depends(require_buyer),
    use_case: ReserveTicketsUseCase = Depends(ReserveTicketsUseCase.depends),
):
    result = await use_case.reserve_tickets(
        event_id=event_id,
        ticket_count=request['ticket_count'],
        buyer_id=current_user.id,
        section=request.get('section'),  # pyright: ignore[reportArgumentType]
        subsection=request.get('subsection'),  # pyright: ignore[reportArgumentType]
    )
    return result
