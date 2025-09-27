import asyncio
from typing import List, Optional

import asyncpg
from fastapi import APIRouter, Depends, Request, status
from sse_starlette.sse import EventSourceResponse

from src.event_ticketing.port.event_schema import (
    EventCreateWithTicketConfigRequest,
    EventResponse,
)
from src.event_ticketing.port.ticket_schema import (
    ListTicketsBySectionResponse,
    TicketResponse,
)
from src.event_ticketing.use_case.create_event_use_case import (
    CreateEventUseCase,
    GetEventUseCase,
    ListEventsUseCase,
)
from src.event_ticketing.use_case.get_availability_use_case import GetAvailabilityUseCase
from src.event_ticketing.use_case.list_tickets_use_case import ListTicketsUseCase
from src.shared.config.core_setting import settings
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import (
    require_buyer_or_seller,
    require_seller,
)
from src.user.infra.user_model import UserModel


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_event(
    request: EventCreateWithTicketConfigRequest,
    current_user: UserModel = Depends(require_seller),
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
@Logger.io(truncate_content=True)
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


@router.get('/{event_id}/sse/status')
@Logger.io(truncate_content=True)
async def sse_event_with_all_subsections_tickets_status(
    request: Request,
    event_id: int,
    current_user: UserModel = Depends(require_buyer_or_seller),
    availability_use_case: GetAvailabilityUseCase = Depends(GetAvailabilityUseCase.depends),
):
    async def event_generator():
        # Send initial connection message
        yield {
            'event': 'connected',
            'data': {
                'message': 'SSE connection established',
                'event_id': event_id,
                'user_id': current_user.id,
            },
        }

        # Send initial status
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
            return

        # Set up database listener for real-time notifications
        listen_conn = None
        last_status = initial_status
        last_sent_time = asyncio.get_event_loop().time()
        notification_received = asyncio.Event()

        def notification_callback(connection, pid, channel, payload):
            """Called when a notification is received - just signal that we got one"""
            notification_received.set()

        try:
            # Create dedicated asyncpg connection for LISTEN/NOTIFY
            # Convert asyncpg URL format (remove +asyncpg part)
            database_url = settings.DATABASE_URL_ASYNC.replace(
                'postgresql+asyncpg://', 'postgresql://'
            )
            listen_conn = await asyncpg.connect(database_url)

            # Add listener for ticket status changes for this event
            channel_name = f'ticket_status_change_{event_id}'
            await listen_conn.add_listener(channel_name, notification_callback)

            while True:
                try:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break

                    # Wait for database notification or timeout after 30 seconds for keepalive
                    try:
                        await asyncio.wait_for(notification_received.wait(), timeout=30.0)
                        notification_received.clear()

                        # Got a notification - fetch updated status with debouncing
                        current_time = asyncio.get_event_loop().time()
                        if (current_time - last_sent_time) >= 0.5:
                            current_status = await availability_use_case.get_event_status_with_all_subsections_tickets_count(
                                event_id=event_id
                            )

                            # Send update if status actually changed
                            if current_status != last_status:
                                yield {
                                    'event': 'status_update',
                                    'data': {
                                        'event_id': event_id,
                                        'timestamp': current_time,
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
                                            for pg in current_status.price_groups
                                        ],
                                    },
                                }
                                last_status = current_status
                                last_sent_time = current_time

                    except asyncio.TimeoutError:
                        # No notification received - send keepalive ping
                        yield {
                            'event': 'ping',
                            'data': {'timestamp': asyncio.get_event_loop().time()},
                        }

                except asyncio.CancelledError:
                    break

        except Exception as e:
            yield {'event': 'error', 'data': {'message': f'Database listener error: {str(e)}'}}

        finally:
            # Clean up database connection
            if listen_conn:
                try:
                    await listen_conn.remove_listener(channel_name, notification_callback)  # pyright: ignore[reportPossiblyUnboundVariable]
                    await listen_conn.close()
                except:
                    pass

        # Send disconnect message
        yield {
            'event': 'disconnected',
            'data': {'message': 'SSE connection closed', 'event_id': event_id},
        }

    return EventSourceResponse(
        event_generator(),
        headers={
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control',
        },
        ping=30,
    )


@router.get(
    '/{event_id}/sse/tickets/section/{section}/subsection/{subsection}',
    status_code=status.HTTP_200_OK,
)
@Logger.io(truncate_content=True)
async def sse_list_tickets_by_event_section_subsection(
    event_id: int,
    section: str,
    subsection: int,
    use_case: ListTicketsUseCase = Depends(ListTicketsUseCase.depends),
) -> ListTicketsBySectionResponse:
    tickets = await use_case.list_tickets_by_event_section_section(
        event_id=event_id,
        section=section,
        subsection=subsection,
    )

    ticket_responses = [_ticket_to_response(ticket) for ticket in tickets]

    return ListTicketsBySectionResponse(
        tickets=ticket_responses,
        total_count=len(ticket_responses),
        event_id=event_id,
        section=section,
        subsection=subsection,
    )


@router.get(
    '/{event_id}/tickets/section/{section}/subsection/{subsection}',
    status_code=status.HTTP_200_OK,
)
@Logger.io(truncate_content=True)
async def list_tickets_by_event_section_subsection(
    event_id: int,
    section: str,
    subsection: int,
    use_case: ListTicketsUseCase = Depends(ListTicketsUseCase.depends),
) -> ListTicketsBySectionResponse:
    tickets = await use_case.list_tickets_by_event_section_section(
        event_id=event_id,
        section=section,
        subsection=subsection,
    )

    ticket_responses = [_ticket_to_response(ticket) for ticket in tickets]

    return ListTicketsBySectionResponse(
        tickets=ticket_responses,
        total_count=len(ticket_responses),
        event_id=event_id,
        section=section,
        subsection=subsection,
    )
