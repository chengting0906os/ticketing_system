"""
Seat Reservation Controller
處理座位預訂相關的 API 端點，包括實時狀態更新
"""

import anyio
import asyncpg
from dependency_injector.wiring import inject
from fastapi import APIRouter, Depends, Request, status
from sse_starlette.sse import EventSourceResponse

from src.event_ticketing.port.ticket_schema import (
    ListTicketsBySectionResponse,
    TicketResponse,
)
from src.seat_reservation.infra.rocksdb_monitor import RocksDBMonitor
from src.seat_reservation.use_case.get_seat_availability_use_case import GetSeatAvailabilityUseCase
from src.seat_reservation.use_case.list_seats_use_case import ListSeatsUseCase
from src.shared.config.core_setting import settings
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.domain.user_entity import UserEntity
from src.shared_kernel.user.use_case.role_auth_service import require_buyer_or_seller


router = APIRouter(prefix='/api/seat_reservation', tags=['seat-reservation'])


def _ticket_to_response(ticket) -> TicketResponse:
    """將票據實體轉換為響應格式"""
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
@inject
async def sse_event_seat_status(
    request: Request,
    event_id: int,
    current_user: UserEntity = Depends(require_buyer_or_seller),
    availability_use_case: GetSeatAvailabilityUseCase = Depends(GetSeatAvailabilityUseCase.depends),
):
    """
    實時座位狀態 SSE 端點
    從 RocksDB 和 PostgreSQL 聚合座位狀態信息
    """

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
        last_sent_time = anyio.current_time()
        notification_received = anyio.Event()

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
                        with anyio.fail_after(30.0):
                            await notification_received.wait()
                        notification_received.clear()

                        # Got a notification - fetch updated status with debouncing
                        current_time = anyio.current_time()
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

                    except anyio.get_cancelled_exc_class():
                        # No notification received - send keepalive ping
                        yield {
                            'event': 'ping',
                            'data': {'timestamp': anyio.current_time()},
                        }

                except anyio.get_cancelled_exc_class():
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
    '/{event_id}/tickets/section/{section}/subsection/{subsection}',
    status_code=status.HTTP_200_OK,
)
@Logger.io(truncate_content=True)
@inject
async def list_seats_by_section_subsection(
    event_id: int,
    section: str,
    subsection: int,
    use_case: ListSeatsUseCase = Depends(ListSeatsUseCase.depends),
) -> ListTicketsBySectionResponse:
    """
    列出指定區域和子區域的所有座位
    從 PostgreSQL 獲取座位信息，結合 RocksDB 狀態
    """
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


# RocksDB 監控端點
monitor = RocksDBMonitor()


@router.get('/rocksdb/events/{event_id}/stats')
async def get_event_stats(event_id: int):
    """
    獲取特定活動的統計資料
    從 RocksDB 聚合座位狀態統計
    """
    stats = monitor.get_event_statistics(event_id)
    if not stats:
        return {'error': f'No data found for event {event_id}'}

    return {
        'event_id': stats.event_id,
        'total_seats': stats.total_seats,
        'available_seats': stats.available_seats,
        'reserved_seats': stats.reserved_seats,
        'sold_seats': stats.sold_seats,
        'sections': stats.sections,
    }


@router.get('/rocksdb/events/{event_id}/seats/reserved')
async def get_reserved_seats(event_id: int):
    """
    獲取特定活動的預訂座位
    用於查看當前預訂狀況
    """
    all_seats = monitor.get_all_seats(limit=5000)
    reserved_seats = [
        seat.to_dict()
        for seat in all_seats
        if seat.event_id == event_id and seat.status == 'RESERVED'
    ]

    return {'event_id': event_id, 'reserved_seats': reserved_seats, 'count': len(reserved_seats)}
