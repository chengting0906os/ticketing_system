from collections.abc import AsyncGenerator
from typing import List, Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.query.list_all_subsection_status_use_case import (
    ListAllSubSectionStatusUseCase,
)
from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.app.query.list_events_use_case import ListEventsUseCase
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.driving_adapter.http_controller.auth.role_auth import require_seller
from src.service.ticketing.driving_adapter.schema.event_schema import (
    EventCreateWithTicketConfigRequest,
    EventResponse,
    EventStateSseResponse,
    SeatResponse,
    SectionStatsResponse,
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


@router.get('/{event_id}', status_code=status.HTTP_200_OK)
@Logger.io
async def get_event_with_subsection_status(event_id: int) -> dict:
    """Get event details with seat status for all subsections (read from Kvrocks)."""
    # Check if event exists first
    repo = container.event_ticketing_query_repo()
    event_aggregate = await repo.get_event_aggregate_by_id_with_tickets(event_id=event_id)
    if event_aggregate is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    event = event_aggregate.event
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    subsection_status = await use_case.execute(event_id=event_id)

    return {
        'id': event_id,
        'name': event.name,
        'description': event.description,
        'seller_id': event.seller_id,
        'is_active': event.is_active,
        'status': event.status.value,
        'venue_name': event.venue_name,
        'seating_config': event.seating_config,
        'sections': subsection_status['sections'],
        'total_sections': subsection_status['total_sections'],
    }


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
    """List all seats in the specified section (query from DB)."""
    repo = container.event_ticketing_query_repo()

    # Check if event exists
    event_aggregate = await repo.get_event_aggregate_by_id_with_tickets(event_id=event_id)
    if event_aggregate is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    # Query tickets from DB
    tickets = await repo.get_tickets_by_subsection(
        event_id=event_id, section=section, subsection=subsection
    )

    # Group seats by status
    seats_by_status: dict[str, list[str]] = {}
    price = 0
    available_count = 0
    reserved_count = 0
    sold_count = 0

    for ticket in tickets:
        seat_position = f'{ticket.row}-{ticket.seat}'
        status_value = ticket.status.value
        if price == 0:
            price = ticket.price

        if status_value not in seats_by_status:
            seats_by_status[status_value] = []
        seats_by_status[status_value].append(seat_position)

        if status_value == 'available':
            available_count += 1
        elif status_value == 'reserved':
            reserved_count += 1
        elif status_value == 'sold':
            sold_count += 1

    total_count = len(tickets)

    # Create SeatResponse for each status group
    seats = [
        SeatResponse(
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_positions=positions,
            price=price,
            status=seat_status,
        )
        for seat_status, positions in seats_by_status.items()
    ]

    return SectionStatsResponse(
        total=total_count,
        available=available_count,
        reserved=reserved_count,
        sold=sold_count,
        event_id=event_id,
        section=section,
        subsection=subsection,
        tickets=seats,
        total_count=total_count,
    )


# ============================ SSE Endpoints (Pub/Sub Subscribe) ============================


@router.get('/{event_id}/sse', status_code=status.HTTP_200_OK)
@Logger.io
async def stream_event_status(
    event_id: int,
) -> EventSourceResponse:
    """SSE real-time push of event status updates (via Redis Pub/Sub subscribe)."""
    # Check if event exists
    repo = container.event_ticketing_query_repo()
    event_aggregate = await repo.get_event_aggregate_by_id_with_tickets(event_id=event_id)
    if event_aggregate is None:
        raise HTTPException(status_code=404, detail=f'Event not found: {event_id}')

    event = event_aggregate.event
    pubsub_handler = container.pubsub_handler()
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    initial_result = await use_case.execute(event_id=event_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            # 1. Send initial status with event info
            initial_response = EventStateSseResponse(
                event_type='initial_status',
                event_id=event_id,
                name=event.name,
                description=event.description,
                seller_id=event.seller_id,
                is_active=event.is_active,
                status=event.status.value,
                venue_name=event.venue_name,
                seating_config=event.seating_config,
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
                    name=event.name,
                    description=event.description,
                    seller_id=event.seller_id,
                    is_active=event.is_active,
                    status=event.status.value,
                    venue_name=event.venue_name,
                    seating_config=event.seating_config,
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
