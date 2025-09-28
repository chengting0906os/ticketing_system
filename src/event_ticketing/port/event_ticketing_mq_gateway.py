"""
Booking Event Gateway Port

【最小可行原則 MVP】
- 這是什麼：處理 booking 事件的業務接口
- 為什麼需要：定義事件處理的業務契約，與基礎設施解耦
- 核心概念：Gateway 模式 + 依賴反轉
- 使用場景：ticketing 服務接收 booking 服務的事件並回應
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from src.event_ticketing.use_case.command.reserve_tickets_use_case import ReserveTicketsUseCase
from src.shared.constant.topic import Topic
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.unified_mq_publisher import publish_domain_event


@dataclass
class BookingCreatedCommand:
    """預訂創建命令"""

    booking_id: int
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    quantity: int

    @classmethod
    @Logger.io
    def from_event_data(cls, event_data: Dict[str, Any]) -> 'BookingCreatedCommand':
        """從事件數據創建命令"""
        aggregate_id = event_data.get('aggregate_id')
        data = event_data.get('data', {})

        if not aggregate_id or not data.get('buyer_id') or not data.get('event_id'):
            raise ValueError('Missing required fields in event data')

        return cls(
            booking_id=int(aggregate_id),
            buyer_id=data.get('buyer_id'),
            event_id=data.get('event_id'),
            section=data.get('section', ''),
            subsection=data.get('subsection', 0),
            quantity=data.get('quantity', 2),
        )


@dataclass
class ProcessingResult:
    """處理結果"""

    is_success: bool
    booking_id: int
    buyer_id: int  # 新增：需要追蹤 buyer_id
    ticket_ids: Optional[List[int]] = None
    error_message: Optional[str] = None

    @property
    def data(self) -> Dict[str, Any]:
        """返回成功時的數據"""
        return {
            'booking_id': self.booking_id,
            'buyer_id': self.buyer_id,
            'ticket_ids': self.ticket_ids or [],
        }


class EventTicketingMqGateway:
    """
    預訂事件網關實現

    【MVP Gateway 職責】
    1. 接收外部事件
    2. 調用業務邏輯 (ReserveTicketsUseCase)
    3. 發送回應事件
    4. 錯誤處理
    """

    def __init__(self, reserve_tickets_use_case: ReserveTicketsUseCase):
        """
        初始化預訂事件網關

        Args:
            reserve_tickets_use_case: 票務預訂 Use Case
        """
        self.reserve_tickets_use_case = reserve_tickets_use_case

    def _parse_event_data(self, event_data: Any) -> Dict[str, Any]:
        """
        強健的事件數據解析，處理多種可能的輸入格式
        """
        try:
            # 如果已經是字典，直接返回
            if isinstance(event_data, dict):
                return event_data

            # 如果是字符串，嘗試 JSON 解析
            elif isinstance(event_data, str):
                return json.loads(event_data)

            # 其他類型，嘗試轉換為字典
            else:
                if hasattr(event_data, '__dict__'):
                    return vars(event_data)
                else:
                    Logger.base.error(f'❌ [GATEWAY] 無法解析事件數據格式: {type(event_data)}')
                    return {}

        except Exception as e:
            Logger.base.error(f'❌ [GATEWAY] 事件數據解析失敗: {e}')
            return {}

    async def can_handle(self, event_type: str) -> bool:
        """檢查是否可以處理指定的事件類型"""
        return event_type == 'BookingCreated'

    async def handle(self, event_data: Any) -> bool:
        """
        處理原始事件數據 (新增的主要入口)

        Args:
            event_data: 原始事件數據

        Returns:
            處理結果
        """
        try:
            # 1. 解析事件數據
            parsed_event_data = self._parse_event_data(event_data)
            if not parsed_event_data:
                Logger.base.error('Failed to parse event data')
                return False

            event_type = parsed_event_data.get('event_type')
            Logger.base.info(f'📨 [GATEWAY] 收到事件: {event_type}')

            # 2. 檢查事件類型
            if not event_type or not await self.can_handle(event_type):
                Logger.base.warning(f'Unknown event type: {event_type}')
                return False

            # 3. 轉換為業務命令
            command = BookingCreatedCommand.from_event_data(parsed_event_data)
            Logger.base.info(f'🎯 [GATEWAY] 處理預訂: booking_id={command.booking_id}')

            # 4. 調用業務邏輯
            result = await self.handle_booking_created(command)

            # 5. 根據結果發送回應
            if result.is_success:
                await self.send_success_response(result)
                Logger.base.info(f'✅ [GATEWAY] 處理成功: booking_id={command.booking_id}')
            else:
                await self.send_failure_response(
                    command.booking_id, command.buyer_id, result.error_message or 'Unknown error'
                )
                Logger.base.error(f'❌ [GATEWAY] 處理失敗: {result.error_message}')

            return result.is_success

        except Exception as e:
            Logger.base.error(f'💥 [GATEWAY] 處理異常: {e}')
            return False

    async def handle_booking_created(self, command: BookingCreatedCommand) -> ProcessingResult:
        try:
            Logger.base.info(
                f'🎫 [GATEWAY] 開始處理預訂: booking_id={command.booking_id}, event_id={command.event_id}, '
                f'section={command.section}, subsection={command.subsection}, quantity={command.quantity}'
            )

            # 直接調用異步 use case，使用從事件中解析的正確參數
            reservation_result = await self.reserve_tickets_use_case.reserve_tickets(
                event_id=command.event_id,
                ticket_count=command.quantity,
                buyer_id=command.buyer_id,
                section=command.section,
                subsection=command.subsection,
            )

            # 提取票務 IDs
            ticket_ids = [ticket['id'] for ticket in reservation_result.get('tickets', [])]

            Logger.base.info(f'✅ [GATEWAY] 票務預訂成功: ticket_ids={ticket_ids}')

            return ProcessingResult(
                is_success=True,
                booking_id=command.booking_id,
                buyer_id=command.buyer_id,
                ticket_ids=ticket_ids,
            )

        except Exception as e:
            Logger.base.error(f'❌ [GATEWAY] 票務預訂失敗: {e}')
            return ProcessingResult(
                is_success=False,
                booking_id=command.booking_id,
                buyer_id=command.buyer_id,
                error_message=str(e),
            )

    async def send_success_response(self, result: ProcessingResult) -> None:
        """
        發送成功回應事件

        Args:
            result: 成功的處理結果
        """

        @dataclass
        class TicketsReserved:
            booking_id: int
            buyer_id: int
            ticket_ids: List[int]
            status: str = 'reserved'
            occurred_at: datetime = datetime.now(timezone.utc)

            @property
            def aggregate_id(self) -> int:
                return self.booking_id

        event = TicketsReserved(
            booking_id=result.booking_id,
            buyer_id=result.buyer_id,  # 修復: 使用來自 result 的 buyer_id
            ticket_ids=result.ticket_ids or [],
        )

        await publish_domain_event(
            event=event,
            topic=Topic.TICKETING_BOOKING_RESPONSE.value,
            partition_key=str(result.booking_id),
        )

        Logger.base.info(
            f'📡 [GATEWAY] 發送成功回應: booking_id={result.booking_id}, buyer_id={result.buyer_id}'
        )

    async def send_failure_response(
        self, booking_id: int, buyer_id: int, error_message: str
    ) -> None:
        """
        發送失敗回應事件

        Args:
            booking_id: 預訂ID
            buyer_id: 買家ID
            error_message: 錯誤信息
        """

        @dataclass
        class TicketReservationFailed:
            booking_id: int
            buyer_id: int  # 新增：失敗事件也需要 buyer_id
            error_message: str
            status: str = 'failed'
            occurred_at: datetime = datetime.now(timezone.utc)

            @property
            def aggregate_id(self) -> int:
                return self.booking_id

        event = TicketReservationFailed(
            booking_id=booking_id, buyer_id=buyer_id, error_message=error_message
        )

        await publish_domain_event(
            event=event, topic=Topic.TICKETING_BOOKING_RESPONSE.value, partition_key=str(booking_id)
        )

        Logger.base.info(
            f'📡 [GATEWAY] 發送失敗回應: booking_id={booking_id}, buyer_id={buyer_id}, error={error_message}'
        )
