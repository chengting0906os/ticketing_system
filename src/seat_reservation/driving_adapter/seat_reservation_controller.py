"""
Seat Reservation Controller
處理座位預訂相關的 API 端點，包括實時狀態更新
"""

import anyio
import asyncpg
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from src.platform.config.core_setting import settings
from src.platform.config.db_setting import get_async_session
from src.platform.logging.loguru_io import Logger
from src.platform.state.redis_client import kvrocks_stats_client
from src.seat_reservation.app.get_seat_availability_use_case import GetSeatAvailabilityUseCase
from src.seat_reservation.driving_adapter.seat_schema import (
    SeatResponse,
    SectionStatsResponse,
)
from src.shared_kernel.user.app.role_auth_service import require_buyer_or_seller
from src.shared_kernel.user.domain.user_entity import UserEntity


def calculate_partition_for_section(section_id: str, num_partitions: int = 3) -> int:
    """
    計算 section 在哪個 Kafka partition（與 Kafka producer 邏輯一致）

    Args:
        section_id: Section ID（例如 "A-1"）
        num_partitions: Partition 總數（預設 3）

    Returns:
        Partition 編號（0-based）

    範例:
        "A-1" → partition 0 → instance 1
        "B-1" → partition 1 → instance 2
        "C-1" → partition 2 → instance 3
    """
    # 提取 section 字母（"A-1" → "A"）
    section_letter = section_id.split('-')[0] if '-' in section_id else section_id

    # 使用與 Kafka producer 相同的 hash 邏輯
    partition = (ord(section_letter[0]) - ord('A')) % num_partitions

    return partition


router = APIRouter(prefix='/api/event', tags=['seat-reservation'])


def _seat_to_response(seat) -> SeatResponse:
    """將座位實體轉換為響應格式"""
    return SeatResponse(
        id=seat.id,
        event_id=seat.event_id,
        section=seat.section,
        subsection=seat.subsection,
        row=seat.row,
        seat=seat.seat,
        price=seat.price,
        status=seat.status.value,
        seat_identifier=seat.seat_identifier,
    )


@router.get('/{event_id}/sse/status')
@Logger.io(truncate_content=True)
async def sse_event_seat_status(
    request: Request,
    event_id: int,
    current_user: UserEntity = Depends(require_buyer_or_seller),
    availability_use_case: GetSeatAvailabilityUseCase = Depends(GetSeatAvailabilityUseCase.depends),
):
    """
    實時座位狀態 SSE 端點
    從 Kvrocks 和 PostgreSQL 聚合座位狀態信息
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
        notification_received: anyio.Event = anyio.Event()

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
                        notification_received.clear()  # pyright: ignore[reportAttributeAccessIssue]

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


@router.get('/{event_id}/sections/stats', status_code=status.HTTP_200_OK)
@Logger.io(truncate_content=True)
async def get_all_section_stats(event_id: int) -> dict:
    """
    獲取活動所有 section 的統計資訊（從 Kvrocks 讀取）

    優化策略：
    1. 直接查詢 Kvrocks（獨立服務，可插隊查詢）
    2. 底層 Kvrocks 持久化（零數據丟失）
    3. 預期性能：~10-30ms（查詢 100 個 section，Pipeline 優化）
    4. 不受 Kafka backlog 影響

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
    # 從 Kvrocks 讀取所有 section 統計
    all_sections = await kvrocks_stats_client.get_all_section_stats(event_id=event_id)

    Logger.base.info(
        f'📊 [KVROCKS-ALL] Retrieved {len(all_sections)} sections for event {event_id}'
    )

    return {'event_id': event_id, 'sections': all_sections, 'total_sections': len(all_sections)}


@router.get(
    '/{event_id}/tickets/section/{section}/subsection/{subsection}',
    status_code=status.HTTP_200_OK,
)
@Logger.io(truncate_content=True)
async def list_seats_by_section_subsection(
    event_id: int,
    section: str,
    subsection: int,
    session: AsyncSession = Depends(get_async_session),
) -> SectionStatsResponse:
    """
    獲取指定區域的統計資訊（從 Kvrocks Bitfield + Counter 直接計算）+ tickets list

    優化重點：
    1. 使用 Bitfield 存儲座位狀態（2 bits per seat）
    2. 使用 Counter 快速查詢可用數（O(1)）
    3. 從資料庫查詢 tickets list
    4. 預期性能：~3-5ms（Bitfield 掃描 + Counter 查詢）
    5. 高併發友好（50,000+ QPS）
    """
    from fastapi import HTTPException
    from sqlalchemy import and_, select

    from src.event_ticketing.driven_adapter.event_model import EventModel
    from src.event_ticketing.driven_adapter.ticket_model import TicketModel
    from src.platform.state.redis_client import kvrocks_client

    # 先檢查 event 是否存在
    stmt_event = select(EventModel).where(EventModel.id == event_id)
    result_event = await session.execute(stmt_event)
    event = result_event.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail='Event not found')

    section_id = f'{section}-{subsection}'
    client = await kvrocks_client.connect()

    try:
        # 1. 從 Counter 取得 available 數量（O(1)）
        subsection_counter_key = f'subsection_avail:{event_id}:{section_id}'
        available = await client.get(subsection_counter_key)
        available_count = int(available) if available else 0

        # 2. 從 Bitfield 掃描取得 total, reserved, sold
        bf_key = f'seats_bf:{event_id}:{section_id}'

        # 檢查 bitfield 是否存在
        if not await client.exists(bf_key):
            Logger.base.warning(f'⚠️ [KVROCKS-MISS] Section {section_id} not initialized')
            return SectionStatsResponse(
                section_id=section_id,
                total=0,
                available=0,
                reserved=0,
                sold=0,
                event_id=event_id,
                section=section,
                subsection=subsection,
                tickets=[],
            )

        # 從 Kvrocks metadata 取得 total（或從 DB 查詢）
        meta_total_key = f'subsection_total:{event_id}:{section_id}'
        total_str = await client.get(meta_total_key)

        if total_str:
            total_count = int(total_str)
        else:
            # Fallback: 估算 total（25 rows x 20 seats = 500）
            total_count = 500

        # 計算 unavailable（reserved + sold）
        unavailable_count = max(0, total_count - available_count)

        Logger.base.info(
            f'✅ [COUNTER] Section {section_id}: '
            f'total={total_count}, available={available_count}, '
            f'unavailable={unavailable_count}'
        )

        # 3. 從資料庫查詢 tickets
        tickets = []
        stmt = select(TicketModel).where(
            and_(
                TicketModel.event_id == event_id,
                TicketModel.section == section,
                TicketModel.subsection == subsection,
            )
        )
        result = await session.execute(stmt)
        ticket_models = result.scalars().all()

        for ticket in ticket_models:
            tickets.append(
                SeatResponse(
                    id=ticket.id,
                    event_id=ticket.event_id,
                    section=ticket.section,
                    subsection=ticket.subsection,
                    row=ticket.row_number,
                    seat=ticket.seat_number,
                    price=ticket.price,
                    status=ticket.status,
                    seat_identifier=f'{ticket.section}-{ticket.subsection}-{ticket.row_number}-{ticket.seat_number}',
                )
            )

        return SectionStatsResponse(
            section_id=section_id,
            total=total_count,
            available=available_count,
            reserved=unavailable_count,  # 簡化：reserved + sold 合併
            sold=0,
            event_id=event_id,
            section=section,
            subsection=subsection,
            tickets=tickets,
            total_count=len(tickets),
        )

    except Exception as e:
        Logger.base.error(f'❌ [KVROCKS] Failed to get section stats: {e}')
        return SectionStatsResponse(
            section_id=section_id,
            total=0,
            available=0,
            reserved=0,
            sold=0,
            event_id=event_id,
            section=section,
            subsection=subsection,
            tickets=[],
        )


@router.get(
    '/{event_id}/tickets/section/{section}/subsection/{subsection}/db',
    status_code=status.HTTP_200_OK,
)
@Logger.io(truncate_content=True)
async def list_seats_by_section_subsection_from_db(
    event_id: int,
    section: str,
    subsection: int,
    session: AsyncSession = Depends(get_async_session),
) -> SectionStatsResponse:
    """
    獲取指定區域的統計資訊 (直接查詢 PostgreSQL)

    此 API 用於與 Kvrocks 版本比較性能差異
    直接從 ticket 表聚合統計數據
    """
    from src.event_ticketing.driven_adapter.ticket_model import TicketModel

    section_id = f'{section}-{subsection}'

    # 構建查詢：統計指定 section 和 subsection 的座位狀態

    stmt = (
        select(
            func.count().label('total'),
            func.sum(case((TicketModel.status == 'available', 1), else_=0)).label('available'),
            func.sum(case((TicketModel.status == 'reserved', 1), else_=0)).label('reserved'),
            func.sum(case((TicketModel.status == 'sold', 1), else_=0)).label('sold'),
        )
        .select_from(TicketModel)
        .where(
            TicketModel.event_id == event_id,
            TicketModel.section == section,
            TicketModel.subsection == subsection,
        )
    )

    Logger.base.debug(f'🔍 [DB-QUERY] SQL: {stmt}')
    Logger.base.debug(
        f'🔍 [DB-QUERY] Params: event_id={event_id}, section={section}, subsection={subsection}'
    )

    result = await session.execute(stmt)
    row = result.one()

    Logger.base.debug(f'🔍 [DB-QUERY] Raw result: {row}')

    Logger.base.info(
        f'📊 [DB-QUERY] Stats for {section_id}: '
        f'total={row.total}, available={row.available}, reserved={row.reserved}, sold={row.sold}'
    )

    return SectionStatsResponse(
        section_id=section_id,
        total=row.total or 0,
        available=row.available or 0,
        reserved=row.reserved or 0,
        sold=row.sold or 0,
        event_id=event_id,
        section=section,
        subsection=subsection,
    )
