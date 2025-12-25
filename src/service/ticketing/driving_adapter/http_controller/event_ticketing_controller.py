from collections.abc import AsyncGenerator
from typing import List, Optional

import attrs
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.app.query.get_event_use_case import GetEventUseCase
from src.service.ticketing.app.query.list_events_use_case import ListEventsUseCase
from src.service.ticketing.app.query.list_subsection_seats_use_case import (
    ListSubsectionSeatsUseCase,
)
from src.service.ticketing.app.query.stream_event_status_use_case import StreamEventStatusUseCase
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.driving_adapter.http_controller.auth.role_auth import require_seller
from src.service.ticketing.domain.enum.sse_event_type import SseEventType
from src.service.ticketing.driving_adapter.schema.event_schema import (
    EventCreateWithTicketConfigRequest,
    EventResponse,
    EventStateSseResponse,
    EventStateSseUpdateResponse,
    EventWithSubsectionStatsResponse,
    SubsectionSeatsResponse,
    TicketResponse,
)


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_event(
    request: EventCreateWithTicketConfigRequest,
    current_user: UserEntity = Depends(require_seller),
    use_case: CreateEventAndTicketsUseCase = Depends(CreateEventAndTicketsUseCase.depends),
) -> EventResponse:
    if not current_user.id:
        raise HTTPException(status_code=400, detail='Invalid user ID')

    event_aggregate = await use_case.create_event_and_tickets(
        name=request.name,
        description=request.description,
        seller_id=current_user.id,
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
        stats=event.stats,
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
                    stats=event.stats,
                )
            )
    return result


# ============================ Seat Status Endpoints ============================


@router.get('/{event_id}', status_code=status.HTTP_200_OK)
@Logger.io
async def get_event_with_subsection_status(
    event_id: int,
    use_case: GetEventUseCase = Depends(GetEventUseCase.depends),
) -> EventWithSubsectionStatsResponse:
    """Get event details with seat status for all subsections."""
    event_aggregate = await use_case.get_by_id(event_id=event_id)
    if event_aggregate is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    event = event_aggregate.event

    return EventWithSubsectionStatsResponse(
        id=event_id,
        name=event.name,
        description=event.description,
        seller_id=event.seller_id,
        is_active=event.is_active,
        status=event.status.value,
        venue_name=event.venue_name,
        seating_config=event.seating_config,
        stats=event.stats,
        sections=[attrs.asdict(stat) for stat in event_aggregate.subsection_stats],
    )


@router.get(
    '/{event_id}/sections/{section}/subsection/{subsection}/seats',
    status_code=status.HTTP_200_OK,
)
@Logger.io
async def list_subsection_seats(
    event_id: int,
    section: str,
    subsection: int,
    use_case: ListSubsectionSeatsUseCase = Depends(ListSubsectionSeatsUseCase.depends),
) -> SubsectionSeatsResponse:
    """List all seats in the specified subsection."""
    aggregate = await use_case.execute(event_id=event_id, section=section, subsection=subsection)

    if aggregate is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    stats = aggregate.stats
    return SubsectionSeatsResponse(
        event_id=stats.event_id,
        section=stats.section,
        subsection=stats.subsection,
        price=stats.price,
        total=stats.total,
        available=stats.available,
        reserved=stats.reserved,
        sold=stats.sold,
        tickets=[
            TicketResponse(
                id=t.id,
                event_id=t.event_id,
                section=t.section,
                subsection=t.subsection,
                row=t.row,
                seat=t.seat,
                price=t.price,
                status=t.status.value,
            )
            for t in aggregate.tickets
        ],
    )


# ============================ SSE Endpoints (Pub/Sub Subscribe) ============================


@router.get('/{event_id}/sse', status_code=status.HTTP_200_OK)
@Logger.io
async def stream_event_status(
    event_id: int,
    use_case: StreamEventStatusUseCase = Depends(StreamEventStatusUseCase.depends),
) -> EventSourceResponse:
    """SSE real-time push of event status updates (via Redis Pub/Sub subscribe)."""
    event_aggregate = await use_case.get_event(event_id=event_id)
    if event_aggregate is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    async def event_generator(
        aggregate: EventTicketingAggregate,
    ) -> AsyncGenerator[dict, None]:
        async for data in use_case.stream(event_id=event_id, event_aggregate=aggregate):
            event_type = data['event_type']
            if event_type == SseEventType.INITIAL_STATUS:
                response = EventStateSseResponse(
                    event_type=event_type.value,
                    event_id=data['event_id'],
                    name=data['name'],
                    description=data['description'],
                    seller_id=data['seller_id'],
                    is_active=data['is_active'],
                    status=data['status'].value,
                    venue_name=data['venue_name'],
                    seating_config=data['seating_config'],
                    sections=[attrs.asdict(stat) for stat in data['subsection_stats']],
                    stats=data['stats'],
                )
            else:
                response = EventStateSseUpdateResponse(
                    event_type=event_type.value,
                    event_id=data['event_id'],
                    stats=data['stats'],
                    subsection_stats=data['subsection_stats'],
                )
            yield {
                'event': event_type.value,
                'data': response.model_dump_json(),
            }

    return EventSourceResponse(event_generator(event_aggregate))
