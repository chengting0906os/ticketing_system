"""
Request Booking Use Case - 發起訂票請求到 Event-Ticketing Service
"""

from typing import List, Optional
import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_publisher import publish_domain_event
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_user_repo
from src.user.domain.user_repo import UserRepo


class RequestBookingUseCase:
    """
    處理訂票請求 - 不直接創建 booking，而是發送請求到 event-ticketing service
    """

    def __init__(
        self,
        session: AsyncSession,
        user_repo: UserRepo,
    ):
        self.session = session
        self.user_repo = user_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        user_repo: UserRepo = Depends(get_user_repo),
    ):
        return cls(session, user_repo)

    @Logger.io
    async def request_booking(
        self,
        *,
        buyer_id: int,
        event_id: int,
        ticket_count: int,
        seat_selection_mode: Optional[str] = None,
        selected_seats: Optional[List[str]] = None,
        quantity: Optional[int] = None,
    ) -> dict:
        """
        發起訂票請求

        Args:
            buyer_id: 買方 ID
            event_id: 活動 ID
            ticket_count: 票數
            seat_selection_mode: 座位選擇模式 ('manual' 或 'best_available')
            selected_seats: 指定座位列表 (manual 模式使用)
            quantity: 票數 (best_available 模式使用)

        Returns:
            包含 request_id 的字典，用於追蹤請求狀態
        """
        # 驗證買方存在
        buyer = await self.user_repo.get_by_id(user_id=buyer_id)
        if not buyer:
            raise DomainError('Buyer not found', 404)

        # 驗證參數
        if ticket_count <= 0:
            raise DomainError('Ticket count must be positive', 400)

        if ticket_count > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)

        # 生成唯一的請求 ID
        request_id = str(uuid.uuid4())

        # 準備請求數據
        request_data = {
            'request_id': request_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'ticket_count': ticket_count,
        }

        # 添加座位選擇信息（如果有）
        if seat_selection_mode:
            request_data.update(
                {
                    'seat_selection_mode': seat_selection_mode,
                    'selected_seats': selected_seats,
                    'quantity': quantity,
                }
            )

        # 創建並發布訂票請求事件
        booking_request_event = {
            'event_type': 'BookingRequested',
            'aggregate_id': buyer_id,  # Use buyer_id as aggregate_id
            'data': request_data,
        }

        # 使用 event_id 作為 partition key 確保同一活動的請求順序處理
        partition_key = f'booking-requests-{event_id}'

        # 發布到 event-ticketing service
        await publish_domain_event(
            event=booking_request_event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_REQUEST,
            partition_key=partition_key,
        )

        return {
            'request_id': request_id,
            'status': 'pending',
            'message': 'Booking request submitted successfully',
            'buyer_id': buyer_id,
            'event_id': event_id,
            'ticket_count': ticket_count,
        }
