"""
Seat Reservation Controller
處理座位預訂相關的 API 端點，包括實時狀態更新
"""

import anyio
import orjson
from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.query.list_all_subsection_status_use_case import (
    ListAllSubSectionStatusUseCase,
)
from src.service.seat_reservation.app.query.list_section_seats_detail_use_case import (
    ListSectionSeatsDetailUseCase,
)
from src.service.seat_reservation.driving_adapter.seat_schema import (
    SeatResponse,
    SectionStatsResponse,
)


router = APIRouter(prefix='/api/reservation', tags=['seat-reservation'])


@router.get('/{event_id}/all_subsection_status', status_code=status.HTTP_200_OK)
@Logger.io
async def list_event_all_subsection_status(event_id: int) -> dict:
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
    列出指定區域的所有座位（僅從 Kvrocks 查詢）

    Architecture: Controller → UseCase → Handler → Kvrocks

    Seat Reservation Service 邊界：
    - ✅ 只存取 Kvrocks（座位狀態的 source of truth）
    - ❌ 不存取 PostgreSQL（Event/Ticket 屬於 Ticketing Service）

    返回資料：
    - 統計數據：total, available, reserved, sold
    - 座位列表：每個座位的 section, subsection, row, seat, price, status

    優化重點：
    1. 從 Bitfield 讀取座位狀態（2 bits per seat）
    2. 從 Hash 讀取價格 metadata
    3. 預期性能：~10-20ms（掃描整個 subsection 的所有座位）
    """
    # Controller → UseCase → Handler (正確分層架構)
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListSectionSeatsDetailUseCase(seat_state_handler=seat_state_handler)

    result = await use_case.execute(event_id=event_id, section=section, subsection=subsection)

    # 轉換為 Response Schema
    seats = [
        SeatResponse(
            event_id=result['event_id'],
            section=seat['section'],
            subsection=seat['subsection'],
            row=seat['row'],
            seat=seat['seat_num'],
            price=seat['price'],
            status=seat['status'],  # 已在底層統一為小寫
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
async def stream_all_section_stats(event_id: int):
    """
    SSE 即時推送所有 section 的統計資料（每 0.5 秒輪詢）

    Architecture: Controller → UseCase → Handler → Kvrocks (polling every 0.5s)

    使用方式：
    ```javascript
    const eventSource = new EventSource('/api/event/1/all_subsection_status/sse');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Event type:', data.event_type);
        console.log('Sections:', data.sections);
    };
    ```

    返回資料格式（JSON）：
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

    優化重點：
    1. 輪詢間隔：0.5 秒（平衡即時性和系統負載）
    2. 直接查詢 Kvrocks（低延遲 ~10-30ms）
    3. 首次推送標記為 initial_status，後續為 status_update
    """

    # Verify event exists before starting SSE stream
    seat_state_handler = container.seat_state_query_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    initial_result = await use_case.execute(event_id=event_id)

    # If event has no sections, it likely doesn't exist
    if initial_result['total_sections'] == 0:
        raise HTTPException(status_code=404, detail='Event not found')

    async def event_generator():
        """產生 SSE 事件流"""
        is_first_event = True

        try:
            while True:
                try:
                    # 查詢所有 section 的狀態
                    result = await use_case.execute(event_id=event_id)

                    # 構建 response data
                    event_type = 'initial_status' if is_first_event else 'status_update'
                    response_data = {
                        'event_type': event_type,
                        'event_id': result['event_id'],
                        'sections': result['sections'],
                        'total_sections': result['total_sections'],
                    }

                    # 發送 SSE 事件
                    yield {'event': event_type, 'data': orjson.dumps(response_data).decode()}

                    is_first_event = False

                    # 等待 0.5 秒
                    await anyio.sleep(0.5)

                except Exception as e:
                    Logger.base.error(f'❌ [SSE] Error streaming all sections: {e}')
                    # 發送錯誤訊息
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
):
    """
    SSE 即時推送座位狀態更新（每 0.5 秒輪詢）

    Architecture: Controller → UseCase → Handler → Kvrocks (polling every 0.5s)

    使用方式：
    ```javascript
    const eventSource = new EventSource('/api/event/1/sections/A/subsection/1/seats/sse');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Seat updates:', data);
    };
    ```

    返回資料格式（JSON）：
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

    優化重點：
    1. 輪詢間隔：0.5 秒（平衡即時性和系統負載）
    2. 直接查詢 Kvrocks（低延遲 ~10-20ms）
    3. 客戶端自動重連機制
    """

    async def event_generator():
        """產生 SSE 事件流"""
        seat_state_handler = container.seat_state_query_handler()
        use_case = ListSectionSeatsDetailUseCase(seat_state_handler=seat_state_handler)

        try:
            while True:
                try:
                    # 查詢座位狀態
                    result = await use_case.execute(
                        event_id=event_id, section=section, subsection=subsection
                    )

                    # 轉換為 Response Schema
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

                    # 發送 SSE 事件
                    yield {'data': orjson.dumps(response_data).decode()}

                    # 等待 0.5 秒
                    await anyio.sleep(0.5)

                except Exception as e:
                    Logger.base.error(f'❌ [SSE] Error streaming seats: {e}')
                    # 發送錯誤訊息
                    yield {'data': orjson.dumps({'error': str(e)}).decode()}
                    await anyio.sleep(0.5)

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'🔌 [SSE] Client disconnected: {section}-{subsection}')
            raise

    return EventSourceResponse(event_generator())
