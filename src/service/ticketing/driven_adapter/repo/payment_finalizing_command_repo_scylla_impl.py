"""
Payment Finalizing Command Repository - ScyllaDB Implementation

付款確認命令倉儲 - 負責將預訂座位標記為已付款
"""

from typing import Optional
from uuid import UUID

from opentelemetry import trace

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface import IPaymentFinalizingCommandRepo


class PaymentFinalizingCommandRepoScyllaImpl(IPaymentFinalizingCommandRepo):
    """
    付款確認命令倉儲 - ScyllaDB 實作

    職責：將座位狀態從 RESERVED 更新為 SOLD（付款完成）
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def finalize_payment(
        self, *, seat_id: str, event_id: UUID, timestamp: Optional[str] = None
    ) -> bool:
        """
        標記座位為已付款

        Args:
            seat_id: 座位 ID (格式: "section-subsection-row-seat")
            event_id: 活動 ID
            timestamp: 可選的時間戳

        Returns:
            是否成功
        """
        Logger.base.info(f'💳 [SCYLLA] Finalizing payment for seat {seat_id}')

        with self.tracer.start_as_current_span(
            'db.finalize_payment',
            attributes={
                'db.system': 'scylladb',
                'db.operation': 'update',
                'db.statement': 'UPDATE ticket SET status=sold WHERE...',
                'seat.id': seat_id,
                'event.id': str(event_id),
            },
        ):
            try:
                parts = seat_id.split('-')
                if len(parts) != 4:
                    Logger.base.warning(f'⚠️ [SCYLLA] Invalid seat_id format: {seat_id}')
                    return False

                section, subsection, row, seat_num = parts

                session = await get_scylla_session()
                update_query = """
                    UPDATE ticket
                    SET status = 'sold',
                        updated_at = toTimestamp(now())
                    WHERE event_id = %s
                      AND section = %s
                      AND subsection = %s
                      AND row_number = %s
                      AND seat_number = %s
                """
                session.execute(
                    update_query, (event_id, section, int(subsection), int(row), int(seat_num))
                )

                Logger.base.info(f'✅ [SCYLLA] Payment finalized for seat {seat_id}')
                return True

            except Exception as e:
                Logger.base.error(f'❌ [SCYLLA] Error finalizing payment for seat {seat_id}: {e}')
                return False
