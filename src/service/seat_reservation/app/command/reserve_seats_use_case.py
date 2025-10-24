"""
Reserve Seats Use Case
座位預訂用例 - 基於 Lua 腳本的原子性操作
"""

from dataclasses import dataclass
from typing import List, Optional

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler
from src.service.seat_reservation.app.interface.i_seat_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)


@dataclass
class ReservationRequest:
    """座位預訂請求"""

    booking_id: int
    buyer_id: int
    event_id: int
    selection_mode: str  # 'manual' or 'best_available'
    quantity: Optional[int] = None
    seat_positions: Optional[List[str]] = None  # 手動選擇的座位ID列表
    section_filter: Optional[str] = None
    subsection_filter: Optional[int] = None


@dataclass
class ReservationResult:
    """座位預訂結果"""

    success: bool
    booking_id: int
    reserved_seats: Optional[List[str]] = None
    total_price: int = 0
    error_message: Optional[str] = None
    event_id: Optional[int] = None


class ReserveSeatsUseCase:
    """
    座位預訂用例

    使用 Lua 腳本在 Kvrocks 中原子性地：
    1. manual mode: 預訂指定座位
    2. best_available mode: 查找並預訂連續座位
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateCommandHandler,
        mq_publisher: ISeatReservationEventPublisher,
    ):
        self.seat_state_handler = seat_state_handler
        self.mq_publisher = mq_publisher

    @Logger.io
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        執行座位預訂 - 直接使用 Lua 腳本原子性操作

        流程：
        1. 驗證請求
        2. 根據模式調用對應的 Lua 腳本：
           - manual: 預訂指定座位
           - best_available: 自動查找並預訂連續座位
        3. 處理結果並發送事件

        Args:
            request: 預訂請求

        Returns:
            預訂結果
        """
        try:
            Logger.base.info(
                f'🎯 [RESERVE] Processing reservation for booking {request.booking_id}, '
                f'buyer {request.buyer_id}, event {request.event_id}'
            )

            # 1. 驗證請求
            self._validate_request(request)

            # 2. 統一調用 Command Handler（Lua 腳本處理冪等性和座位預訂）
            result = await self.seat_state_handler.reserve_seats_atomic(
                event_id=request.event_id,
                booking_id=request.booking_id,
                buyer_id=request.buyer_id,
                mode=request.selection_mode,
                seat_ids=request.seat_positions if request.selection_mode == 'manual' else None,
                section=request.section_filter,  # 兩種模式都需要 section
                subsection=request.subsection_filter,  # 兩種模式都需要 subsection
                quantity=request.quantity if request.selection_mode == 'best_available' else None,
            )

            # 3. 處理結果並發送事件（price 已由 reserve_seats_atomic 從 Kvrocks 獲取）
            if result['success']:
                reserved_seats = result['reserved_seats']
                ticket_price = result.get('ticket_price', 0)

                Logger.base.info(
                    f'✅ [RESERVE] Successfully reserved {len(reserved_seats)} seats '
                    f'for booking {request.booking_id}, price={ticket_price}'
                )

                # 計算總價格（所有座位價格相同）
                total_price = ticket_price * len(reserved_seats)

                # 建立包含價格的 ticket 資訊
                ticket_details = [
                    {'seat_id': seat_id, 'price': ticket_price} for seat_id in reserved_seats
                ]

                # 發送座位預訂成功事件（包含完整的 ticket 資訊和價格）
                await self.mq_publisher.publish_seats_reserved(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    reserved_seats=reserved_seats,
                    total_price=total_price,
                    event_id=request.event_id,
                    ticket_details=ticket_details,
                )

                return ReservationResult(
                    success=True,
                    booking_id=request.booking_id,
                    reserved_seats=reserved_seats,
                    total_price=total_price,
                    event_id=request.event_id,
                )
            else:
                error_msg = result.get('error_message', 'Reservation failed')

                # 發送座位預訂失敗事件
                await self.mq_publisher.publish_reservation_failed(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )

                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )

        except DomainError as e:
            Logger.base.warning(f'⚠️ [RESERVE] Domain error: {e}')
            error_msg = str(e)

            await self.mq_publisher.publish_reservation_failed(
                booking_id=request.booking_id,
                buyer_id=request.buyer_id,
                error_message=error_msg,
                event_id=request.event_id,
            )

            return ReservationResult(
                success=False,
                booking_id=request.booking_id,
                error_message=error_msg,
                event_id=request.event_id,
            )
        except Exception as e:
            Logger.base.error(f'❌ [RESERVE] Unexpected error: {e}')
            error_msg = 'Internal server error'

            await self.mq_publisher.publish_reservation_failed(
                booking_id=request.booking_id,
                buyer_id=request.buyer_id,
                error_message=error_msg,
                event_id=request.event_id,
            )

            return ReservationResult(
                success=False,
                booking_id=request.booking_id,
                error_message=error_msg,
                event_id=request.event_id,
            )

    def _validate_request(self, request: ReservationRequest) -> None:
        """驗證預訂請求"""
        if request.selection_mode == 'manual':
            if not request.seat_positions:
                raise DomainError('Manual selection requires seat positions', 400)
            if len(request.seat_positions) > 6:
                raise DomainError('Cannot reserve more than 6 seats at once', 400)

        elif request.selection_mode == 'best_available':
            if not request.quantity or request.quantity <= 0:
                raise DomainError('Best available selection requires valid quantity', 400)
            if request.quantity > 6:
                raise DomainError('Cannot reserve more than 6 seats at once', 400)
            if not request.section_filter or request.subsection_filter is None:
                raise DomainError('Best available mode requires section and subsection filter', 400)

        else:
            raise DomainError(f'Invalid selection mode: {request.selection_mode}', 400)
