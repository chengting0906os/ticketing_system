"""
RocksDB 監控服務
用於座位預訂系統的 RocksDB 狀態監控
"""

from dataclasses import asdict, dataclass
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

try:
    from quixstreams import Application

    QUIX_STREAMS_AVAILABLE = True
except ImportError:
    QUIX_STREAMS_AVAILABLE = False
    Application = None

from src.shared.logging.loguru_io import Logger


@dataclass
class SeatState:
    """座位狀態資料類"""

    seat_id: str
    status: str
    event_id: Optional[int] = None
    price: Optional[int] = None
    booking_id: Optional[int] = None
    buyer_id: Optional[int] = None
    reserved_at: Optional[int] = None
    sold_at: Optional[int] = None
    initialized_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EventStats:
    """活動統計資料類"""

    event_id: int
    total_seats: int
    available_seats: int
    reserved_seats: int
    sold_seats: int
    sections: Dict[str, Dict[str, int]]


class RocksDBMonitor:
    """Quix Streams RocksDB 監控器"""

    def __init__(self, state_dir: str = './rocksdb_state'):
        self.state_dir = Path(state_dir)
        self.app = None
        # 延遲初始化，只在需要時才設置

    def _setup_application(self) -> None:
        """設置 Quix Streams Application 用於狀態讀取"""
        if not QUIX_STREAMS_AVAILABLE:
            Logger.base.warning('📂 [MONITOR] Quix Streams not available')
            return

        try:
            if not QUIX_STREAMS_AVAILABLE or Application is None:
                return

            from src.shared.config.core_setting import settings

            self.app = Application(
                broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
                consumer_group='monitoring-reader',
                auto_offset_reset='latest',
                state_dir=str(self.state_dir),
                auto_create_topics=False,  # 不自動創建 topics
            )
            Logger.base.info(
                f'🔍 [MONITOR] Quix Streams Application setup with state dir: {self.state_dir}'
            )
        except Exception as e:
            Logger.base.error(f'❌ [MONITOR] Failed to setup Quix Streams: {e}')
            self.app = None

    def is_available(self) -> bool:
        """檢查 Quix Streams 是否可用"""
        if not QUIX_STREAMS_AVAILABLE:
            return False

        # 延遲初始化
        if self.app is None:
            self._setup_application()

        return self.app is not None

    def get_all_seats(self, limit: int = 1000) -> List[SeatState]:
        """獲取所有座位狀態 (使用狀態目錄檔案讀取)"""
        if not self.is_available():
            return []

        try:
            # 直接讀取狀態目錄中的檔案
            if not self.state_dir.exists():
                Logger.base.warning(f'📂 [MONITOR] State directory not found: {self.state_dir}')
                return []

            # 尋找 RocksDB 狀態檔案
            state_files = list(self.state_dir.rglob('*.sst')) + list(
                self.state_dir.rglob('CURRENT')
            )

            if not state_files:
                Logger.base.info(f'📂 [MONITOR] No RocksDB state files found in {self.state_dir}')
                return []

            Logger.base.info(
                f'🔍 [MONITOR] Found {len(state_files)} state files, using mock data for now'
            )

            # 暫時返回模擬資料，因為直接讀取 RocksDB 需要不同的實現
            # TODO: 實現真實的 Quix Streams 狀態讀取
            mock_seats = [
                SeatState(
                    seat_id='A-1-1-1',
                    status='AVAILABLE',
                    event_id=1,
                    price=1000,
                    initialized_at=int(time.time()),
                ),
                SeatState(
                    seat_id='A-1-1-2',
                    status='RESERVED',
                    event_id=1,
                    price=1000,
                    booking_id=12345,
                    buyer_id=67890,
                    reserved_at=int(time.time()) - 300,
                ),
                SeatState(
                    seat_id='A-1-1-3',
                    status='SOLD',
                    event_id=1,
                    price=1000,
                    booking_id=12346,
                    buyer_id=67891,
                    sold_at=int(time.time()) - 600,
                ),
            ]

            return mock_seats[: min(limit, len(mock_seats))]

        except Exception as e:
            Logger.base.error(f'❌ [MONITOR] Error reading seats: {e}')
            return []

    def get_event_statistics(self, event_id: int) -> Optional[EventStats]:
        """獲取特定活動的統計資料"""
        all_seats = self.get_all_seats()
        event_seats = [seat for seat in all_seats if seat.event_id == event_id]

        if not event_seats:
            return None

        available = len([s for s in event_seats if s.status == 'AVAILABLE'])
        reserved = len([s for s in event_seats if s.status == 'RESERVED'])
        sold = len([s for s in event_seats if s.status == 'SOLD'])

        sections = {}
        for seat in event_seats:
            try:
                parts = seat.seat_id.split('-')
                if len(parts) >= 1:
                    section = parts[0]
                    if section not in sections:
                        sections[section] = {'available': 0, 'reserved': 0, 'sold': 0}
                    sections[section][seat.status.lower()] += 1
            except:
                continue

        return EventStats(
            event_id=event_id,
            total_seats=len(event_seats),
            available_seats=available,
            reserved_seats=reserved,
            sold_seats=sold,
            sections=sections,
        )

    def get_system_health(self) -> Dict[str, Any]:
        """獲取系統健康狀態"""
        health = {
            'quix_streams_available': self.is_available(),
            'state_dir': str(self.state_dir),
            'app_configured': self.app is not None,
            'timestamp': int(time.time()),
        }

        if self.is_available():
            try:
                all_seats = self.get_all_seats(limit=100)
                status_dist = {}
                for seat in all_seats:
                    status = seat.status
                    status_dist[status] = status_dist.get(status, 0) + 1

                health.update(
                    {'total_seats_sample': len(all_seats), 'status_distribution': status_dist}
                )
            except Exception as e:
                health['error'] = str(e)

        return health
