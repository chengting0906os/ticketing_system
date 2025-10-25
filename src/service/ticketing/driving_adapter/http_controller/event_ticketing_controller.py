from typing import Dict, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status

from src.platform.config.di import Container
from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface import ISeatStateQueryHandler
from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.app.query.get_event_use_case import GetEventUseCase
from src.service.ticketing.app.query.list_events_use_case import ListEventsUseCase
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.driving_adapter.http_controller.auth.role_auth import require_seller
from src.service.ticketing.driving_adapter.schema.event_schema import (
    EventCreateWithTicketConfigRequest,
    EventResponse,
    TicketResponse,
)


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
@inject
async def create_event(
    request: EventCreateWithTicketConfigRequest,
    current_user: UserEntity = Depends(require_seller),
    use_case: CreateEventAndTicketsUseCase = Depends(
        Provide[Container.create_event_and_tickets_use_case]
    ),
) -> EventResponse:
    event_aggregate = await use_case.create_event_and_tickets(
        name=request.name,
        description=request.description,
        seller_id=current_user.id or 0,  # Use current user's ID
        venue_name=request.venue_name,
        seating_config=request.seating_config,
        is_active=request.is_active,
    )

    # Extract event entity for better readability
    event = event_aggregate.event

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
@inject
async def get_event(
    event_id: int,
    use_case: GetEventUseCase = Depends(Provide[Container.get_event_use_case]),
    seat_query_handler: ISeatStateQueryHandler = Depends(
        Provide[Container.seat_state_query_handler]
    ),
) -> EventResponse:
    event_aggregate = await use_case.get_by_id(event_id=event_id)

    if not event_aggregate:
        raise NotFoundError(f'Event with id {event_id} not found')

    # Extract event entity for better readability
    event = event_aggregate.event

    # Get seat availability stats from Kvrocks via shared_kernel interface
    seat_stats = await seat_query_handler.list_all_subsection_status(event_id=event_id)

    # Merge seat availability into seating_config
    enhanced_seating_config = _merge_seat_stats_into_config(event.seating_config, seat_stats)

    # Get all tickets for this event
    tickets = await use_case.event_ticketing_query_repo.get_all_tickets_by_event(event_id=event_id)
    ticket_responses = [
        TicketResponse(
            id=ticket.id or 0,
            event_id=ticket.event_id,
            section=ticket.section,
            subsection=ticket.subsection,
            row=ticket.row,
            seat=ticket.seat,
            price=ticket.price,
            status=ticket.status.value,
            seat_identifier=ticket.seat_identifier,
            buyer_id=ticket.buyer_id,
        )
        for ticket in tickets
    ]

    return EventResponse(
        id=event_id,
        name=event.name,
        description=event.description,
        seller_id=event.seller_id,
        venue_name=event.venue_name,
        seating_config=enhanced_seating_config,
        is_active=event.is_active,
        status=event.status.value,
        tickets=ticket_responses,
    )


def _merge_seat_stats_into_config(seating_config: Dict, seat_stats: Dict[str, Dict]) -> Dict:
    """Merge seat availability statistics into seating configuration."""
    enhanced_config = seating_config.copy()

    if 'sections' not in enhanced_config:
        return enhanced_config

    for section in enhanced_config['sections']:
        section_name = section['name']

        if 'subsections' not in section:
            continue

        for subsection in section['subsections']:
            subsection_number = subsection['number']
            section_id = f'{section_name}-{subsection_number}'

            # Get stats for this subsection from Kvrocks
            if section_id in seat_stats:
                stats = seat_stats[section_id]
                subsection['available'] = stats['available']
                subsection['reserved'] = stats['reserved']
                subsection['sold'] = stats['sold']
                subsection['total'] = stats['total']
            else:
                # Default values if stats not found
                subsection['available'] = 0
                subsection['reserved'] = 0
                subsection['sold'] = 0
                subsection['total'] = 0

    return enhanced_config


@router.get('', status_code=status.HTTP_200_OK)
@Logger.io
@inject
async def list_events(
    seller_id: Optional[int] = None,
    use_case: ListEventsUseCase = Depends(Provide[Container.list_events_use_case]),
) -> List[EventResponse]:
    if seller_id is not None:
        events = await use_case.get_by_seller(seller_id)
    else:
        events = await use_case.list_available()

    result = []
    for event_aggregate in events:
        # Extract event entity for better readability
        event = event_aggregate.event
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
