"""
Seat Reservation Gateway
座位預訂閘道 - 處理票券預訂請求並協調座位選擇

【最小可行原則 MVP】
- 這是什麼：處理票券預訂請求的業務接口
- 為什麼需要：執行座位選擇算法並協調服務間溝通
- 核心概念：Gateway 模式 + 依賴反轉
- 使用場景：接收 booking 服務的預訂請求，執行座位選擇，回傳結果
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from src.seat_reservation.use_case.reserve_seats_use_case import (
    ReservationRequest,
    ReserveSeatsUseCase,
)
from src.shared.logging.loguru_io import Logger
from src.shared_infra.message_queue.event_publisher import publish_domain_event
from src.shared_infra.message_queue.kafka_constant_builder import KafkaTopicBuilder


@dataclass
class TicketReserveCommand:
    """票券預訂命令"""

    booking_id: int
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: List[str]

    @classmethod
    @Logger.io
    def from_event_data(cls, event_data: Dict[str, Any]) -> 'TicketReserveCommand':
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
            seat_selection_mode=data.get('seat_selection_mode', 'best_available'),
            seat_positions=data.get('seat_positions', []),
        )


@dataclass
class SeatReservationResult:
    """座位預訂處理結果"""

    is_success: bool
    booking_id: int
    buyer_id: int
    reserved_seats: Optional[List[str]] = None
    total_price: int = 0
    error_message: Optional[str] = None

    @property
    def data(self) -> Dict[str, Any]:
        """返回成功時的數據"""
        return {
            'booking_id': self.booking_id,
            'buyer_id': self.buyer_id,
            'reserved_seats': self.reserved_seats or [],
            'total_price': self.total_price,
        }


class SeatReservationGateway:
    """
    座位預訂事件網關實現

    【MVP Gateway 職責】
    1. 接收票券預訂請求
    2. 調用座位選擇業務邏輯 (ReserveSeatsUseCase)
    3. 發送座位預訂結果事件
    4. 錯誤處理
    """

    def __init__(self, reserve_seats_use_case: ReserveSeatsUseCase):
        """
        初始化座位預訂事件網關

        Args:
            reserve_seats_use_case: 座位預訂 Use Case
        """
        self.reserve_seats_use_case = reserve_seats_use_case

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

    async def handle_event(self, event_data: Any) -> bool:
        """
        處理原始事件數據 (主要入口)

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
            Logger.base.info(f'📨 [SEAT-GATEWAY] 收到事件: {event_type}')

            # 3. 轉換為業務命令
            command = TicketReserveCommand.from_event_data(parsed_event_data)
            Logger.base.info(f'🎯 [SEAT-GATEWAY] 處理座位預訂: booking_id={command.booking_id}')

            # 4. 調用業務邏輯
            result = await self.handle_ticket_reserve_request(command)

            # 5. 根據結果發送回應
            if result.is_success:
                await self.send_success_response(result, event_id=command.event_id)
                Logger.base.info(f'✅ [SEAT-GATEWAY] 座位預訂成功: booking_id={command.booking_id}')
            else:
                await self.send_failure_response(
                    command.booking_id,
                    command.buyer_id,
                    result.error_message or 'Unknown error',
                    event_id=command.event_id,
                )
                Logger.base.error(f'❌ [SEAT-GATEWAY] 座位預訂失敗: {result.error_message}')

            return result.is_success

        except Exception as e:
            Logger.base.error(f'💥 [SEAT-GATEWAY] 處理異常: {e}')
            return False

    async def handle_ticket_reserve_request(
        self, command: TicketReserveCommand
    ) -> SeatReservationResult:
        try:
            Logger.base.info(
                f'🪑 [SEAT-GATEWAY] 開始座位選擇: booking_id={command.booking_id}, event_id={command.event_id}, '
                f'section={command.section}, subsection={command.subsection}, quantity={command.quantity}, '
                f'mode={command.seat_selection_mode}'
            )

            # 轉換為 UseCase 的請求格式
            reservation_request = ReservationRequest(
                booking_id=command.booking_id,
                buyer_id=command.buyer_id,
                event_id=command.event_id,
                selection_mode=command.seat_selection_mode,
                quantity=command.quantity,
                seat_positions=command.seat_positions,
                section_filter=command.section,
                subsection_filter=command.subsection,
            )

            # 調用座位預訂用例
            use_case_result = await self.reserve_seats_use_case.reserve_seats(reservation_request)

            if use_case_result.success:
                Logger.base.info(
                    f'✅ [SEAT-GATEWAY] 座位選擇成功: seats={use_case_result.reserved_seats}'
                )

                return SeatReservationResult(
                    is_success=True,
                    booking_id=command.booking_id,
                    buyer_id=command.buyer_id,
                    reserved_seats=use_case_result.reserved_seats,
                    total_price=use_case_result.total_price,
                )
            else:
                return SeatReservationResult(
                    is_success=False,
                    booking_id=command.booking_id,
                    buyer_id=command.buyer_id,
                    error_message=use_case_result.error_message,
                )

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-GATEWAY] 座位選擇失敗: {e}')
            return SeatReservationResult(
                is_success=False,
                booking_id=command.booking_id,
                buyer_id=command.buyer_id,
                error_message=str(e),
            )

    async def send_success_response(self, result: SeatReservationResult, event_id: int) -> None:
        """發送座位預訂成功回應事件"""

        @dataclass
        class SeatsReserved:
            booking_id: int
            buyer_id: int
            reserved_seats: List[str]
            total_price: int
            status: str = 'seats_reserved'
            occurred_at: datetime = datetime.now(timezone.utc)

            @property
            def aggregate_id(self) -> int:
                return self.booking_id

        event = SeatsReserved(
            booking_id=result.booking_id,
            buyer_id=result.buyer_id,
            reserved_seats=result.reserved_seats or [],
            total_price=result.total_price,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_ticket_status_to_reserved_in_postgresql(
                event_id=event_id
            ),
            partition_key=str(result.booking_id),
        )

        Logger.base.info(
            f'📡 [SEAT-GATEWAY] 發送座位預訂成功回應: booking_id={result.booking_id}, '
            f'seats={len(result.reserved_seats or [])}個'
        )

    async def send_failure_response(
        self, booking_id: int, buyer_id: int, error_message: str, event_id: int
    ) -> None:
        """發送座位預訂失敗回應事件"""

        @dataclass
        class SeatReservationFailed:
            booking_id: int
            buyer_id: int
            error_message: str
            status: str = 'seat_reservation_failed'
            occurred_at: datetime = datetime.now(timezone.utc)

            @property
            def aggregate_id(self) -> int:
                return self.booking_id

        event = SeatReservationFailed(
            booking_id=booking_id, buyer_id=buyer_id, error_message=error_message
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
            partition_key=str(booking_id),
        )

        Logger.base.info(
            f'📡 [SEAT-GATEWAY] 發送座位預訂失敗回應: booking_id={booking_id}, '
            f'buyer_id={buyer_id}, error={error_message}'
        )
