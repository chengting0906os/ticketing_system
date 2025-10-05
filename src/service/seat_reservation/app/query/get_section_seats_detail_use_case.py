"""
Get Section Seats Detail Use Case
獲取某個 section 所有座位詳細狀態的用例
"""

import json
from dataclasses import dataclass
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.event_ticketing.driven_adapter.event_model import EventModel
from src.platform.state.redis_client import kvrocks_stats_client


@dataclass
class SeatDetail:
    """座位詳細資訊"""

    seat_id: str
    status: str
    price: int
    row: int
    seat_num: int


@dataclass
class GetSectionSeatsDetailRequest:
    """獲取座位詳細資訊請求"""

    event_id: int
    section: str
    subsection: int


@dataclass
class GetSectionSeatsDetailResult:
    """獲取座位詳細資訊結果"""

    seats: List[SeatDetail]
    section_id: str
    total_count: int


class GetSectionSeatsDetailUseCase:
    """
    獲取某個 section 所有座位詳細狀態

    從 Kvrocks Bitfield 直接讀取即時座位狀態
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, request: GetSectionSeatsDetailRequest) -> GetSectionSeatsDetailResult:
        """
        執行獲取座位詳細資訊

        Args:
            request: 請求參數

        Returns:
            包含所有座位詳細資訊的結果
        """
        # 1. 從資料庫讀取 event 的 seating_config
        stmt = select(EventModel).where(EventModel.id == request.event_id)
        result = await self.session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            raise ValueError(f'Event {request.event_id} not found')

        # 2. 解析 seating_config 找到對應的 subsection 配置
        seating_config = (
            json.loads(event.seating_config)
            if isinstance(event.seating_config, str)
            else event.seating_config
        )

        max_rows = None
        seats_per_row = None

        for section in seating_config.get('sections', []):
            if section['name'] == request.section:
                for subsection in section.get('subsections', []):
                    if subsection['number'] == request.subsection:
                        max_rows = subsection.get('rows')
                        seats_per_row = subsection.get('seats_per_row')
                        break
                break

        if max_rows is None or seats_per_row is None:
            raise ValueError(
                f'Seating config not found for section {request.section}-{request.subsection} '
                f'in event {request.event_id}'
            )

        # 3. 從 Kvrocks 獲取座位詳細資訊（使用正確的配置）
        seats_data = await kvrocks_stats_client.get_section_seats_detail(
            event_id=request.event_id,
            section=request.section,
            subsection=request.subsection,
            max_rows=max_rows,
            seats_per_row=seats_per_row,
        )

        # 轉換為 domain objects
        seats = [
            SeatDetail(
                seat_id=seat['seat_id'],
                status=seat['status'],
                price=seat['price'],
                row=seat['row'],
                seat_num=seat['seat_num'],
            )
            for seat in seats_data
        ]

        section_id = f'{request.section}-{request.subsection}'

        return GetSectionSeatsDetailResult(
            seats=seats, section_id=section_id, total_count=len(seats)
        )
