"""
Seat Reservation Controller
處理座位預訂相關的 API 端點，包括實時狀態更新
"""

# from src.service.ticketing.app.service.role_auth_service import require_buyer_or_seller
# from src.service.ticketing.domain.entity.user_entity import UserEntity
from fastapi import APIRouter, status

# from sse_starlette.sse import EventSourceResponse
from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.query.list_all_subsection_status_use_case import (
    ListAllSubSectionStatusUseCase,
)


router = APIRouter(prefix='/api/event', tags=['seat-reservation'])


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
    seat_state_handler = container.seat_state_handler()
    use_case = ListAllSubSectionStatusUseCase(seat_state_handler=seat_state_handler)
    return await use_case.execute(event_id=event_id)


# @router.get(
#     '/{event_id}/sections/{section}/subsection/{subsection}/seats',
#     status_code=status.HTTP_200_OK,
# )
# @Logger.io
# async def list_subsection_seats(
#     event_id: int,
#     section: str,
#     subsection: int,
# ) -> SectionStatsResponse:
#     """
#     列出指定區域的所有座位（僅從 Kvrocks 查詢）

#     Seat Reservation Service 邊界：
#     - ✅ 只存取 Kvrocks（座位狀態的 source of truth）
#     - ❌ 不存取 PostgreSQL（Event/Ticket 屬於 Ticketing Service）

#     返回資料：
#     - 統計數據：total, available, reserved, sold
#     - 座位列表：每個座位的 section, subsection, row, seat, price, status（500 個座位）

#     優化重點：
#     1. 從 Bitfield 讀取座位狀態（2 bits per seat）
#     2. 從 Hash 讀取價格 metadata
#     3. 預期性能：~10-20ms（掃描整個 subsection 的所有座位）
#     """

#     section_id = f'{section}-{subsection}'
#     client = await kvrocks_client.connect()

#     # 1. 檢查 bitfield 是否存在（間接驗證 event/section 是否存在）
#     bf_key = f'seats_bf:{event_id}:{section_id}'
#     if not await client.exists(bf_key):
#         Logger.base.warning(f'⚠️ [KVROCKS-MISS] Section {section_id} not initialized')
#         raise HTTPException(
#             status_code=404,
#             detail=f'Section {section_id} for event {event_id} not found in Kvrocks',
#         )

#     # 2. 從 State Handler 獲取所有座位資料
#     seat_state_handler = container.seat_state_handler()
#     seats_data = await seat_state_handler.list_all_subsection_seats(event_id, section, subsection)

#     # 3. 轉換為 SeatResponse
#     tickets = [
#         SeatResponse(
#             event_id=event_id,
#             section=seat['section'],
#             subsection=seat['subsection'],
#             row=seat['row'],
#             seat=seat['seat_num'],
#             price=seat['price'],
#             status=seat['status'],
#             seat_identifier=seat['seat_identifier'],
#         )
#         for seat in seats_data
#     ]

#     # 4. 計算統計數據
#     total_count = len(tickets)
#     available_count = sum(1 for t in tickets if t.status == 'AVAILABLE')
#     unavailable_count = total_count - available_count

#     Logger.base.info(
#         f'✅ [KVROCKS-SEATS] Section {section_id}: '
#         f'total={total_count}, available={available_count}, seats={len(tickets)}'
#     )

#     return SectionStatsResponse(
#         section_id=section_id,
#         total=total_count,
#         available=available_count,
#         reserved=unavailable_count,
#         sold=0,
#         event_id=event_id,
#         section=section,
#         subsection=subsection,
#         tickets=tickets,
#         total_count=len(tickets),
#     )


# ============================ SSE Endpoint (for future use) ============================
