"""
Seat Initializing Command Repository - ScyllaDB Implementation

座位初始化命令倉儲 - 負責座位初始化操作（測試用）
"""

from typing import Optional
from uuid import UUID

from opentelemetry import trace

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface import ISeatInitializingCommandRepo


class SeatInitializingCommandRepoScyllaImpl(ISeatInitializingCommandRepo):
    """
    座位初始化命令倉儲 - ScyllaDB 實作

    職責：初始化座位狀態（主要用於測試）
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def initialize_seat(
        self, *, seat_id: str, event_id: UUID, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """
        初始化座位（用於測試）

        Args:
            seat_id: 座位 ID (格式: "section-subsection-row-seat")
            event_id: 活動 ID
            price: 座位價格
            timestamp: 可選的時間戳

        Returns:
            是否成功
        """
        Logger.base.info(f'🎫 [SCYLLA] Initializing seat {seat_id} with price {price}')

        with self.tracer.start_as_current_span(
            'db.initialize_seat',
            attributes={
                'db.system': 'scylladb',
                'db.operation': 'upsert',
                'seat.id': seat_id,
                'event.id': str(event_id),
                'seat.price': price,
            },
        ):
            try:
                parts = seat_id.split('-')
                if len(parts) != 4:
                    Logger.base.warning(f'⚠️ [SCYLLA] Invalid seat_id format: {seat_id}')
                    return False

                section, subsection, row, seat_num = parts

                session = await get_scylla_session()

                # Check if seat already exists
                with self.tracer.start_as_current_span(
                    'db.check_seat_exists',
                    attributes={
                        'db.statement': 'SELECT * FROM ticket WHERE...',
                    },
                ):
                    check_query = """
                        SELECT * FROM ticket
                        WHERE event_id = %s
                          AND section = %s
                          AND subsection = %s
                          AND row_number = %s
                          AND seat_number = %s
                    """
                    result = session.execute(
                        check_query, (event_id, section, int(subsection), int(row), int(seat_num))
                    )

                if result.one():
                    # Update existing seat
                    with self.tracer.start_as_current_span(
                        'db.update_seat',
                        attributes={
                            'db.statement': 'UPDATE ticket SET status=available WHERE...',
                        },
                    ):
                        update_query = """
                            UPDATE ticket
                            SET status = 'available',
                                price = %s,
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
                            (price, event_id, section, int(subsection), int(row), int(seat_num)),
                        )
                else:
                    # Insert new seat
                    with self.tracer.start_as_current_span(
                        'db.insert_seat',
                        attributes={
                            'db.statement': 'INSERT INTO ticket VALUES...',
                        },
                    ):
                        insert_query = """
                            INSERT INTO ticket (
                                event_id, section, subsection, row_number, seat_number,
                                status, price, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, toTimestamp(now()), toTimestamp(now()))
                        """
                        session.execute(
                            insert_query,
                            (
                                event_id,
                                section,
                                int(subsection),
                                int(row),
                                int(seat_num),
                                'available',
                                price,
                            ),
                        )

                Logger.base.info(f'✅ [SCYLLA] Initialized seat {seat_id}')
                return True

            except Exception as e:
                Logger.base.error(f'❌ [SCYLLA] Error initializing seat {seat_id}: {e}')
                return False
