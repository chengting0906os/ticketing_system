"""
RocksDB 監控服務
用於座位預訂系統的 RocksDB 狀態監控
"""

from dataclasses import asdict, dataclass
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from src.shared.config.core_setting import settings


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

    def _read_from_json_files(self, json_files: list, limit: int) -> List[SeatState]:
        """從 JSON 檔案讀取座位狀態"""
        seats = []

        try:
            import json

            for json_file in json_files:
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)

                    for seat_id, state in data.items():
                        seat = SeatState(
                            seat_id=seat_id,
                            event_id=state.get('event_id', 0),
                            status=state.get('status', 'UNKNOWN'),
                            price=state.get('price', 0),
                            booking_id=state.get('booking_id', 0),
                            buyer_id=state.get('buyer_id', 0),
                            reserved_at=state.get('reserved_at'),
                            sold_at=state.get('sold_at'),
                        )
                        seats.append(seat)

                        # 達到限制數量就停止
                        if len(seats) >= limit:
                            break

                    if len(seats) >= limit:
                        break

                except Exception as e:
                    Logger.base.warning(f'⚠️ [MONITOR] Failed to read JSON file {json_file}: {e}')
                    continue

            Logger.base.info(
                f'📊 [MONITOR] Read {len(seats)} seats from {len(json_files)} JSON files'
            )
            return seats

        except Exception as e:
            Logger.base.error(f'❌ [MONITOR] Failed to read from JSON files: {e}')
            return []
        # 延遲初始化，只在需要時才設置

    def _setup_application(self) -> None:
        """設置 Quix Streams Application 用於狀態讀取"""
        if not QUIX_STREAMS_AVAILABLE:
            Logger.base.warning('📂 [MONITOR] Quix Streams not available')
            return

        try:
            if not QUIX_STREAMS_AVAILABLE or Application is None:
                return

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

            # 尋找 RocksDB 狀態檔案或 JSON 檔案
            rocksdb_files = list(self.state_dir.rglob('*.sst')) + list(
                self.state_dir.rglob('CURRENT')
            )
            json_files = list(self.state_dir.glob('event_*_seats.json'))

            if not rocksdb_files and not json_files:
                Logger.base.info(
                    f'📂 [MONITOR] No RocksDB or JSON state files found in {self.state_dir}'
                )
                return []

            # 如果有 JSON 檔案，優先使用 JSON 檔案
            if json_files:
                return self._read_from_json_files(json_files, limit)

            Logger.base.info(
                f'🔍 [MONITOR] Found {len(rocksdb_files)} RocksDB state files, using mock data for now'
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
