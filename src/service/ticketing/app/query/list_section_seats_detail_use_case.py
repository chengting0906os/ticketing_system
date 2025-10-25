"""
Get Section Seats Detail Use Case
獲取指定 section/subsection 的所有座位詳情
"""

from uuid import UUID

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface import ISeatStateQueryHandler


class ListSectionSeatsDetailUseCase:
    """
    獲取指定區域的所有座位詳情 Use Case

    職責：
    - 驗證 section 是否存在
    - 調用 Handler 獲取座位列表
    - 計算統計資料
    """

    def __init__(self, seat_state_handler: ISeatStateQueryHandler):
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, event_id: UUID, section: str, subsection: int) -> dict:
        """
        執行查詢

        Args:
            event_id: 活動 ID
            section: 區域代碼 (e.g., 'A')
            subsection: 子區域編號 (e.g., 1)

        Returns:
            {
                "section_id": "A-1",
                "event_id": 1,
                "section": "A",
                "subsection": 1,
                "total": 100,
                "available": 80,
                "reserved": 15,
                "sold": 5,
                "seats": [
                    {
                        "section": "A",
                        "subsection": 1,
                        "row": 1,
                        "seat_num": 1,
                        "price": 1000,
                        "status": "AVAILABLE",
                        "seat_identifier": "A-1-1-1"
                    },
                    ...
                ]
            }
        """
        from src.platform.exception.exceptions import NotFoundError

        section_id = f'{section}-{subsection}'

        # 從 Handler 獲取座位列表
        seats_data = await self.seat_state_handler.list_all_subsection_seats(
            event_id=event_id, section=section, subsection=subsection
        )

        # 檢查 event section 是否存在 (空列表表示不存在)
        if not seats_data:
            Logger.base.warning(f'❌ [USE-CASE] Event {event_id} section {section_id} not found')
            raise NotFoundError('Event not found')

        # 計算統計數據
        total_count = len(seats_data)
        available_count = sum(1 for seat in seats_data if seat['status'] == 'available')
        reserved_count = sum(1 for seat in seats_data if seat['status'] == 'reserved')
        sold_count = sum(1 for seat in seats_data if seat['status'] == 'sold')

        Logger.base.info(
            f'✅ [USE-CASE] Section {section_id}: '
            f'total={total_count}, available={available_count}, reserved={reserved_count}, sold={sold_count}'
        )

        return {
            'section_id': section_id,
            'event_id': event_id,
            'section': section,
            'subsection': subsection,
            'total': total_count,
            'available': available_count,
            'reserved': reserved_count,
            'sold': sold_count,
            'seats': seats_data,
        }
