"""
Seat Availability Query Handler Implementation

座位可用性查詢處理器實作 - Adapter for ticketing service to query seat state
"""

import os

from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


# Key prefix for Kvrocks (matches seat_reservation service convention)
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for environment isolation"""
    return f'{_KEY_PREFIX}{key}'


class SeatAvailabilityQueryHandlerImpl(ISeatAvailabilityQueryHandler):
    """
    座位可用性查詢處理器實作

    職責：直接查詢 Kvrocks 獲取座位狀態統計
    不依賴 seat_reservation service 的實現類，保持服務邊界清晰
    """

    # @Logger.io
    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """檢查指定 subsection 是否有足夠的可用座位"""
        Logger.base.info(
            f'🔍 [AVAILABILITY CHECK] Checking {section}-{subsection} '
            f'for event {event_id}, need {required_quantity} seats'
        )

        try:
            # Query Kvrocks directly for single subsection stats (efficient - O(1) vs O(N))
            client = await kvrocks_client.connect()

            # Direct key query - no need to scan all subsections
            section_id = f'{section}-{subsection}'
            stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
            stats = await client.hgetall(stats_key)  # type: ignore

            if not stats:
                Logger.base.warning(
                    f'⚠️  [AVAILABILITY CHECK] Section {section_id} not found for event {event_id}'
                )
                raise NotFoundError(f'Section {section_id} not found')

            available_count = int(stats.get('available', 0))
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
