"""
Seat Releasing Command Repository - ScyllaDB Implementation

座位釋放命令倉儲 - 負責釋放已預訂座位（補償操作）
"""

from typing import Dict, List
from uuid import UUID

from opentelemetry import trace

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface import ISeatReleasingCommandRepo


class SeatReleasingCommandRepoScyllaImpl(ISeatReleasingCommandRepo):
    """
    座位釋放命令倉儲 - ScyllaDB 實作

    職責：釋放已預訂座位，用於補償操作（訂單取消、超時等）
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def release_seats(self, *, seat_ids: List[str], event_id: UUID) -> Dict[str, bool]:
        """
        釋放座位（補償操作）

        Args:
            seat_ids: 座位 ID 列表 (格式: "section-subsection-row-seat")
            event_id: 活動 ID

        Returns:
            Dict[seat_id, success]: 每個座位的釋放結果
        """
        Logger.base.info(f'🔓 [SCYLLA] Releasing {len(seat_ids)} seats for event {event_id}')

        with self.tracer.start_as_current_span(
            'db.release_seats',
            attributes={
                'db.system': 'scylladb',
                'db.operation': 'update',
                'seat.count': len(seat_ids),
                'event.id': str(event_id),
            },
        ):
            session = await get_scylla_session()
            results = {}

            for seat_id in seat_ids:
                try:
                    parts = seat_id.split('-')
                    if len(parts) == 4:
                        section, subsection, row, seat_num = parts
                    else:
                        Logger.base.warning(f'⚠️ [SCYLLA] Invalid seat_id format: {seat_id}')
                        results[seat_id] = False
                        continue

                    with self.tracer.start_as_current_span(
                        'db.release_seat',
                        attributes={
                            'db.statement': 'UPDATE ticket SET status=available WHERE...',
                            'seat.id': seat_id,
                        },
                    ):
                        update_query = """
                            UPDATE ticket
                            SET status = 'available',
                                buyer_id = null,
                                updated_at = toTimestamp(now())
                            WHERE event_id = %s
                              AND section = %s
                              AND subsection = %s
                              AND row_number = %s
                              AND seat_number = %s
                        """
                        session.execute(
                            update_query,
                            (event_id, section, int(subsection), int(row), int(seat_num)),
                        )

                    results[seat_id] = True
                    Logger.base.info(f'✅ [SCYLLA] Released seat: {seat_id}')

                except Exception as e:
                    Logger.base.error(f'❌ [SCYLLA] Error releasing seat {seat_id}: {e}')
                    results[seat_id] = False

            return results
