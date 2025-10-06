"""
Init Event And Tickets State Handler Implementation

座位初始化狀態處理器實作 - 調用 seat_reservation service 的 handler
"""

from typing import Dict

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)
from src.service.seat_reservation.app.interface.i_seat_state_handler import ISeatStateHandler


class InitEventAndTicketsStateHandlerImpl(IInitEventAndTicketsStateHandler):
    """
    座位初始化狀態處理器實作

    職責：
    - 調用 seat_reservation service 的 SeatStateHandler
    - 處理初始化結果並回傳給 Use Case
    """

    def __init__(self, seat_state_handler: ISeatStateHandler):
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: Dict) -> Dict:
        """
        從 seating_config 初始化座位

        Args:
            event_id: 活動 ID
            seating_config: 座位配置

        Returns:
            {
                'success': True/False,
                'total_seats': 3000,
                'sections_count': 30,
                'error': None or error message
            }
        """
        try:
            Logger.base.info(
                f'🚀 [INIT-HANDLER] Delegating to seat_reservation handler for event {event_id}'
            )

            # 調用 seat_reservation service 的 handler
            result = await self.seat_state_handler.initialize_seats_from_config(
                event_id=event_id, seating_config=seating_config
            )

            if result['success']:
                Logger.base.info(
                    f'✅ [INIT-HANDLER] Seat initialization successful: '
                    f'{result["total_seats"]} seats, {result["sections_count"]} sections'
                )
            else:
                Logger.base.error(
                    f'❌ [INIT-HANDLER] Seat initialization failed: {result["error"]}'
                )

            return result

        except Exception as e:
            error_msg = f'Seat initialization error: {str(e)}'
            Logger.base.error(f'❌ [INIT-HANDLER] {error_msg}')
            return {'success': False, 'total_seats': 0, 'sections_count': 0, 'error': error_msg}
