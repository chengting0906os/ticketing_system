"""
Seat Reservation Controller
Handles seat reservation related API endpoints, including real-time status updates
"""

from collections.abc import AsyncGenerator

import anyio
from fastapi import APIRouter, HTTPException, status
import orjson
from src.service.reservation.app.query.list_all_subsection_status_use_case import (
    ListAllSubSectionStatusUseCase,
)
from src.service.reservation.app.query.list_section_seats_detail_use_case import (
    ListSectionSeatsDetailUseCase,
)
from src.service.reservation.driving_adapter.seat_schema import (
    SeatResponse,
    SectionStatsResponse,
)
from sse_starlette.sse import EventSourceResponse

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger


router = APIRouter(tags=['reservation'])


@router.get('/{event_id}/all_subsection_status', status_code=status.HTTP_200_OK)
@Logger.io
async def list_event_all_subsection_status(event_id: int) -> dict:
    """
    Get statistics for all sections of an event (read from Kvrocks)

    Optimization strategy:
    1. Query Kvrocks directly (independent service, can skip queue)
    2. Kvrocks persistence at the bottom layer (zero data loss)
    3. Expected performance: ~10-30ms (querying 100 sections, Pipeline optimized)
    4. Not affected by Kafka backlog

    Returns:
        {
            "event_id": 1,
            "sections": {
                "A-1": {"available": 100, "reserved": 20, "sold": 30, "total": 150},
                ...
            },
            "total_sections": 100
        }
    """
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
    """
    List all seats in the specified section (query from Kvrocks only)

    Architecture: Controller -> UseCase -> Handler -> Kvrocks

    Seat Reservation Service boundary:
    - Only accesses Kvrocks (source of truth for seat state)
    - Does not access PostgreSQL (Event/Ticket belongs to Ticketing Service)

    Return data:
    - Statistics: total, available, reserved, sold
    - Seat list: section, subsection, row, seat, price, status for each seat

    Optimization focus:
    1. Read seat status from Bitfield (2 bits per seat)
    2. Read price metadata from Hash
    3. Expected performance: ~10-20ms (scanning all seats in a subsection)
    """
    # Controller -> UseCase -> Handler (correct layered architecture)
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListSectionSeatsDetailUseCase(seat_state_handler=seat_state_handler)

    result = await use_case.execute(event_id=event_id, section=section, subsection=subsection)

    # Convert to Response Schema
    seats = [
        SeatResponse(
            event_id=result['event_id'],
            section=seat['section'],
            subsection=seat['subsection'],
            row=seat['row'],
            seat=seat['seat_num'],
            price=seat['price'],
            status=seat['status'],  # Already unified to lowercase in the lower layer
            seat_identifier=seat['seat_identifier'],
        )
        for seat in result['seats']
    ]

    return SectionStatsResponse(
        section_id=result['section_id'],
        total=result['total'],
        available=result['available'],
        reserved=result['reserved'],
        sold=result['sold'],
        event_id=result['event_id'],
        section=result['section'],
        subsection=result['subsection'],
        tickets=seats,
        total_count=len(seats),
    )


# ============================ SSE Endpoint ============================


@router.get('/{event_id}/all_subsection_status/sse', status_code=status.HTTP_200_OK)
@Logger.io
async def stream_all_section_stats(event_id: int) -> EventSourceResponse:
    """
    SSE real-time push of statistics for all sections (polling every 0.5 seconds)

    Architecture: Controller -> UseCase -> Handler -> Kvrocks (polling every 0.5s)

    Usage:
    ```javascript
    const eventSource = new EventSource('/api/event/1/all_subsection_status/sse');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Event type:', data.event_type);
        console.log('Sections:', data.sections);
    };
    ```

    Return data format (JSON):
    {
        "event_type": "initial_status" | "status_update",
        "event_id": 1,
        "sections": {
            "A-1": {"total": 100, "available": 95, "reserved": 3, "sold": 2},
            "A-2": {...},
            ...
        },
        "total_sections": 30
    }

    Optimization focus:
    1. Polling interval: 0.5 seconds (balancing real-time and system load)
    2. Query Kvrocks directly (low latency ~10-30ms)
    3. First push marked as initial_status, subsequent as status_update
    """

    # Verify event exists before starting SSE stream
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    initial_result = await use_case.execute(event_id=event_id)

    # If event has no sections, it likely doesn't exist
    if initial_result['total_sections'] == 0:
        raise HTTPException(status_code=404, detail='Event not found')

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE event stream"""
        is_first_event = True

        try:
            while True:
                try:
                    # Query status of all sections
                    result = await use_case.execute(event_id=event_id)

                    # Build response data
                    event_type = 'initial_status' if is_first_event else 'status_update'
                    response_data = {
                        'event_type': event_type,
                        'event_id': result['event_id'],
                        'sections': result['sections'],
                        'total_sections': result['total_sections'],
                    }

                    # Send SSE event
                    yield {'event': event_type, 'data': orjson.dumps(response_data).decode()}

                    is_first_event = False

                    # Wait 0.5 seconds
                    await anyio.sleep(0.5)

                except Exception as e:
                    Logger.base.error(f'❌ [SSE] Error streaming all sections: {e}')
                    # Send error message
                    yield {'data': orjson.dumps({'error': str(e)}).decode()}
                    await anyio.sleep(0.5)

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'🔌 [SSE] Client disconnected from event {event_id}')
            raise

    return EventSourceResponse(event_generator())


@router.get(
    '/{event_id}/sections/{section}/subsection/{subsection}/seats/sse',
    status_code=status.HTTP_200_OK,
)
@Logger.io
async def stream_subsection_seats(
    event_id: int,
    section: str,
    subsection: int,
) -> EventSourceResponse:
    """
    SSE real-time push of seat status updates (polling every 0.5 seconds)

    Architecture: Controller -> UseCase -> Handler -> Kvrocks (polling every 0.5s)

    Usage:
    ```javascript
    const eventSource = new EventSource('/api/event/1/sections/A/subsection/1/seats/sse');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Seat updates:', data);
    };
    ```

    Return data format (JSON):
    {
        "section_id": "A-1",
        "event_id": 1,
        "section": "A",
        "subsection": 1,
        "total": 100,
        "available": 95,
        "reserved": 3,
        "sold": 2,
        "seats": [...]
    }

    Optimization focus:
    1. Polling interval: 0.5 seconds (balancing real-time and system load)
    2. Query Kvrocks directly (low latency ~10-20ms)
    3. Client automatic reconnection mechanism
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE event stream"""
        seat_state_handler = container.seat_state_query_handler()
        use_case = ListSectionSeatsDetailUseCase(seat_state_handler=seat_state_handler)

        try:
            while True:
                try:
                    # Query seat status
                    result = await use_case.execute(
                        event_id=event_id, section=section, subsection=subsection
                    )

                    # Convert to Response Schema
                    seats = [
                        {
                            'event_id': result['event_id'],
                            'section': seat['section'],
                            'subsection': seat['subsection'],
                            'row': seat['row'],
                            'seat': seat['seat_num'],
                            'price': seat['price'],
                            'status': seat['status'],
                            'seat_identifier': seat['seat_identifier'],
                        }
                        for seat in result['seats']
                    ]

                    response_data = {
                        'section_id': result['section_id'],
                        'total': result['total'],
                        'available': result['available'],
                        'reserved': result['reserved'],
                        'sold': result['sold'],
                        'event_id': result['event_id'],
                        'section': result['section'],
                        'subsection': result['subsection'],
                        'tickets': seats,
                        'total_count': result['total'],
                    }

                    # Send SSE event
                    yield {'data': orjson.dumps(response_data).decode()}

                    # Wait 0.5 seconds
                    await anyio.sleep(0.5)

                except Exception as e:
                    Logger.base.error(f'❌ [SSE] Error streaming seats: {e}')
                    # Send error message
                    yield {'data': orjson.dumps({'error': str(e)}).decode()}
                    await anyio.sleep(0.5)

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'🔌 [SSE] Client disconnected: {section}-{subsection}')
            raise

    return EventSourceResponse(event_generator())
