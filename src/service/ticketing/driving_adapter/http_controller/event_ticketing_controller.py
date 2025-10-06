from typing import List, Optional

from fastapi import APIRouter, Depends, status

from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.app.query.get_event_use_case import GetEventUseCase
from src.service.ticketing.app.query.list_events_use_case import ListEventsUseCase
from src.service.ticketing.driving_adapter.schema.event_schema import (
    EventCreateWithTicketConfigRequest,
    EventResponse,
)
from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.service.role_auth_service import require_seller
from src.service.ticketing.domain.entity.user_entity import UserEntity


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_event(
    request: EventCreateWithTicketConfigRequest,
    current_user: UserEntity = Depends(require_seller),
    use_case: CreateEventAndTicketsUseCase = Depends(CreateEventAndTicketsUseCase.depends),
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
async def get_event(
    event_id: int, use_case: GetEventUseCase = Depends(GetEventUseCase.depends)
) -> EventResponse:
    event_aggregate = await use_case.get_by_id(event_id=event_id)

    if not event_aggregate:
        raise NotFoundError(f'Event with id {event_id} not found')

    # Extract event entity for better readability
    event = event_aggregate.event

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
