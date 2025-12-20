from collections.abc import AsyncGenerator
from typing import Dict, List, Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from src.platform.config.di import container
from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.query.list_all_subsection_status_use_case import (
    ListAllSubSectionStatusUseCase,
)
from src.service.reservation.app.query.list_section_seats_detail_use_case import (
    ListSectionSeatsDetailUseCase,
)
from src.service.shared_kernel.app.interface import ISeatStateQueryHandler
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
    EventStateSseResponse,
    SeatResponse,
    SectionStatsResponse,
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
    event_id: int,
    use_case: GetEventUseCase = Depends(GetEventUseCase.depends),
    seat_query_handler: ISeatStateQueryHandler = Depends(
        lambda: __import__(
            'src.platform.config.di', fromlist=['container']
        ).container.seat_state_query_handler()
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
            row_number=ticket.row,
            seat_number=ticket.seat,
            price=ticket.price,
            status=ticket.status.value,
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

    global_rows = enhanced_config.get('rows', 1)
    global_cols = enhanced_config.get('cols', 10)

    for section in enhanced_config['sections']:
        section_name = section['name']
        subsection_count = section.get('subsections', 0)

        expanded_subsections = []
        for num in range(1, subsection_count + 1):
            section_id = f'{section_name}-{num}'
            stats = seat_stats.get(section_id, {})
            expanded_subsections.append(
                {
                    'number': num,
                    'rows': global_rows,
                    'cols': global_cols,
                    'available': stats.get('available', 0),
                    'reserved': stats.get('reserved', 0),
                    'sold': stats.get('sold', 0),
                    'total': stats.get('total', 0),
                }
            )
        section['subsections'] = expanded_subsections

    return enhanced_config


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


# ============================ Seat Status Endpoints ============================


@router.get('/{event_id}/all_subsection_status', status_code=status.HTTP_200_OK)
@Logger.io
async def list_event_all_subsection_status(event_id: int) -> dict:
    """Get statistics for all sections of an event (read from Kvrocks)."""
    # Check if event exists first
    repo = container.event_ticketing_query_repo()
    event = await repo.get_event_aggregate_by_id_with_tickets(event_id=event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    seat_state_handler = container.seat_state_query_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    return await use_case.execute(event_id=event_id)


@router.get(
    '/{event_id}/sections/{section}/subsection/{subsection}/seats',
    status_code=status.HTTP_200_OK,
)
@Logger.io
async def list_subsection_seats(
    event_id: int,
    section: str,
    subsection: int,
) -> SectionStatsResponse:
    """List all seats in the specified section (query from Kvrocks only)."""
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListSectionSeatsDetailUseCase(seat_state_handler=seat_state_handler)

    result = await use_case.execute(event_id=event_id, section=section, subsection=subsection)

    # Create SeatResponse for each status group
    seats = [
        SeatResponse(
            event_id=result['event_id'],
            section=result['section'],
            subsection=result['subsection'],
            seat_positions=positions,
            price=result['price'],
            status=seat_status,
        )
        for seat_status, positions in result['seats_by_status'].items()
    ]

    return SectionStatsResponse(
        total=result['total'],
        available=result['available'],
        reserved=result['reserved'],
        sold=result['sold'],
        event_id=result['event_id'],
        section=result['section'],
        subsection=result['subsection'],
        tickets=seats,
        total_count=result['total'],
    )


# ============================ SSE Endpoints (Pub/Sub Subscribe) ============================


@router.get('/{event_id}/all_subsection_status/sse', status_code=status.HTTP_200_OK)
@Logger.io
async def stream_all_section_stats(
    event_id: int,
) -> EventSourceResponse:
    """SSE real-time push of statistics for all sections (via Redis Pub/Sub subscribe)."""
    # Check if event exists
    repo = container.event_ticketing_query_repo()
    event = await repo.get_event_aggregate_by_id_with_tickets(event_id=event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    pubsub_handler = container.pubsub_handler()
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    initial_result = await use_case.execute(event_id=event_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            # 1. Send initial status
            initial_response = EventStateSseResponse(
                event_type='initial_status',
                event_id=initial_result['event_id'],
                sections=initial_result['sections'],
                total_sections=initial_result['total_sections'],
            )
            yield {
                'event': 'initial_status',
                'data': initial_response.model_dump_json(),
            }

            # 2. Subscribe to pub/sub for updates
            async for payload in pubsub_handler.subscribe_event_state(event_id=event_id):
                event_state = payload.get('event_state', {})
                update_response = EventStateSseResponse(
                    event_type='status_update',
                    event_id=payload.get('event_id', event_id),
                    sections=event_state.get('sections', {}),
                    total_sections=event_state.get('total_sections', 0),
                )
                yield {
                    'event': 'status_update',
                    'data': update_response.model_dump_json(),
                }

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'[SSE] Client disconnected from event {event_id}')
            raise
        except Exception as e:
            Logger.base.error(
                f'[SSE] Error in generator for event {event_id}: {type(e).__name__}: {e}'
            )
            raise

    return EventSourceResponse(event_generator())
