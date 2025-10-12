"""
Seat Availability Query Handler Implementation

座位可用性查詢處理器實作 - Adapter for ticketing service to query seat state
"""

from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.driven_adapter.seat_state_query_handler_impl import (
    SeatStateQueryHandlerImpl,
)
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


class SeatAvailabilityQueryHandlerImpl(ISeatAvailabilityQueryHandler):
    """
    座位可用性查詢處理器實作

    職責：橋接 ticketing service 和 seat_reservation service 的查詢操作
    使用 SeatStateQueryHandlerImpl 來獲取座位狀態統計
    """

    def __init__(self):
        self._seat_state_query_handler = SeatStateQueryHandlerImpl()

    @Logger.io
    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """檢查指定 subsection 是否有足夠的可用座位"""
        Logger.base.info(
            f'🔍 [AVAILABILITY CHECK] Checking {section}-{subsection} '
            f'for event {event_id}, need {required_quantity} seats'
        )

        try:
            # Get all subsection statistics
            all_stats = await self._seat_state_query_handler.list_all_subsection_status(
                event_id=event_id
            )

            section_id = f'{section}-{subsection}'
            stats = all_stats.get(section_id)

            if not stats:
                Logger.base.warning(
                    f'⚠️  [AVAILABILITY CHECK] Section {section_id} not found for event {event_id}'
                )
                raise NotFoundError(f'Section {section_id} not found')

            available_count = stats.get('available', 0)

            has_enough = available_count >= required_quantity

            if has_enough:
                Logger.base.info(
                    f'✅ [AVAILABILITY CHECK] Sufficient seats: {available_count} available, '
                    f'{required_quantity} required'
                )
            else:
                Logger.base.warning(
                    f'❌ [AVAILABILITY CHECK] Insufficient seats: {available_count} available, '
                    f'{required_quantity} required'
                )

            return has_enough

        except NotFoundError:
            raise
        except Exception as e:
            Logger.base.error(f'❌ [AVAILABILITY CHECK] Error checking availability: {e}')
            raise
