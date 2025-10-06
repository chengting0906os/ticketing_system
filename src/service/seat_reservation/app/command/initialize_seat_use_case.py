"""
Initialize Seat Use Case
座位初始化用例
"""

from dataclasses import dataclass

from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.interface.i_seat_state_handler import SeatStateHandler
import time


@dataclass
class InitializeSeatRequest:
    """座位初始化請求"""

    seat_id: str
    event_id: int
    price: int
    timestamp: str
    rows: int  # 總行數
    seats_per_row: int  # 每行座位數


@dataclass
class InitializeSeatResult:
    """座位初始化結果"""

    success: bool
    seat_id: str
    error_message: str = ''


class InitializeSeatUseCase:
    """座位初始化用例 - 負責批量處理策略和性能統計"""

    # 批量處理配置
    BATCH_SIZE = 1000
    BATCH_TIMEOUT = 0.5  # 秒

    def __init__(self, seat_state_handler: SeatStateHandler):
        self.seat_state_handler = seat_state_handler

        # 批量處理狀態
        self.init_batch: list[InitializeSeatRequest] = []
        self.last_batch_time = 0.0

        # 性能統計
        self.batch_count = 0
        self.total_seats_processed = 0
        self.init_start_time: float | None = None

    def _should_flush_batch(self, current_time: float) -> bool:
        """判斷是否需要刷新批次"""
        return (
            len(self.init_batch) >= self.BATCH_SIZE
            or (current_time - self.last_batch_time) >= self.BATCH_TIMEOUT
        )

    async def execute(self, request: InitializeSeatRequest) -> InitializeSeatResult:
        """執行單個座位初始化（內部自動批量處理）"""

        current_time = time.time()

        # 啟動計時器（第一個消息）
        if self.init_start_time is None:
            self.init_start_time = current_time
            Logger.base.info('⏱️  [UC-TIMER] Initialization started')

        # 1. 累積到批次
        self.init_batch.append(request)
        self.total_seats_processed += 1

        # 2. 檢查是否需要刷新
        if self._should_flush_batch(current_time):
            await self._flush_batch(current_time)

        return InitializeSeatResult(success=True, seat_id=request.seat_id)

    async def _flush_batch(self, current_time: float) -> None:
        """刷新批次 - 執行批量初始化"""
        if not self.init_batch:
            return

        batch_size = len(self.init_batch)
        self.batch_count += 1
        batch_start = current_time

        try:
            # 準備批量數據
            seats_data = [
                {
                    'seat_id': req.seat_id,
                    'event_id': req.event_id,
                    'price': req.price,
                }
                for req in self.init_batch
            ]

            # 批量調用 State Handler
            results = await self.seat_state_handler.initialize_seats_batch(seats_data)

            # 計算批次耗時
            batch_elapsed = current_time - batch_start
            success_count = sum(1 for v in results.values() if v)

            # 記錄性能統計
            if self.init_start_time:
                total_elapsed = current_time - self.init_start_time
                rate = self.total_seats_processed / total_elapsed if total_elapsed > 0 else 0

                Logger.base.info(
                    f'✅ [UC-BATCH #{self.batch_count}] '
                    f'{success_count}/{batch_size} seats | '
                    f'Batch: {batch_elapsed:.3f}s | '
                    f'Total: {self.total_seats_processed} seats in {total_elapsed:.2f}s '
                    f'({rate:.0f} seats/sec)'
                )

        except Exception as e:
            Logger.base.error(f'❌ [UC-FLUSH] Batch flush failed: {e}')
        finally:
            # 清空批次並更新時間
            self.init_batch.clear()
            self.last_batch_time = current_time

    async def force_flush(self) -> None:
        """強制刷新批次（在消費結束時調用）"""
        import time

        if self.init_batch:
            Logger.base.info(f'🔄 [UC-FORCE-FLUSH] Flushing remaining {len(self.init_batch)} seats')
            await self._flush_batch(time.time())
