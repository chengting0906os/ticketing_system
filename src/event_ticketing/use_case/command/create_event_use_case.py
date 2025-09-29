"""
Create Event Use Case - 使用新的 EventTicketingAggregate

重構後的活動創建業務邏輯：
- 使用 EventTicketingAggregate 作為聚合根
- 整合活動和票務創建邏輯
- 負責 Kafka 基礎設施初始化
- 處理 RocksDB 座位初始化
"""

import asyncio
import os
from typing import Dict

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.event_ticketing_aggregate import EventTicketingAggregate
from src.event_ticketing.domain.event_ticketing_command_repo import EventTicketingCommandRepo
from src.seat_reservation.infra.rocksdb_monitor import RocksDBMonitor
from src.shared.config.db_setting import get_async_session
from src.shared.config.di import Container
from src.shared.constant.path import BASE_DIR
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.domain.kafka_config_service import KafkaConfigServiceInterface


class CreateEventUseCase:
    def __init__(
        self,
        session: AsyncSession,
        event_ticketing_command_repo: EventTicketingCommandRepo,
        kafka_service: KafkaConfigServiceInterface,
    ):
        self.session = session
        self.event_ticketing_command_repo = event_ticketing_command_repo
        self.kafka_service = kafka_service

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        event_ticketing_command_repo: EventTicketingCommandRepo = Depends(
            Provide[Container.event_ticketing_command_repo]
        ),
        kafka_service: KafkaConfigServiceInterface = Depends(Provide[Container.kafka_service]),
    ):
        return cls(
            session=session,
            event_ticketing_command_repo=event_ticketing_command_repo,
            kafka_service=kafka_service,
        )

    @Logger.io
    async def create_event_and_tickets(
        self,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> EventTicketingAggregate:
        """
        創建活動和票務 - 使用新的聚合根

        Args:
            name: 活動名稱
            description: 活動描述
            seller_id: 賣家 ID
            venue_name: 場地名稱
            seating_config: 座位配置
            is_active: 是否啟用

        Returns:
            創建的 EventTicketingAggregate
        """

        # 1. 創建 EventTicketingAggregate
        event_aggregate = EventTicketingAggregate.create_event_with_tickets(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
        )

        # 2. 保存 Event 以獲得 ID
        saved_aggregate = await self.event_ticketing_command_repo.create_event_aggregate(
            event_aggregate=event_aggregate
        )

        # 3. 生成票務（同時獲得批量插入格式）
        ticket_tuples = saved_aggregate.generate_tickets()
        Logger.base.info(f'Prepared {len(ticket_tuples)} tickets for batch insert')

        # 4. 使用高效能批量創建方法保存 tickets
        final_aggregate = (
            await self.event_ticketing_command_repo.create_event_aggregate_with_batch_tickets(
                event_aggregate=saved_aggregate,
                ticket_tuples=ticket_tuples,  # 傳入預先準備好的資料
            )
        )

        # 5. 啟用活動 (從 DRAFT 轉為 AVAILABLE)
        final_aggregate.activate()

        # 6. 更新活動狀態到資料庫
        final_aggregate = await self.event_ticketing_command_repo.update_event_aggregate(
            event_aggregate=final_aggregate
        )

        if not final_aggregate.event.id:
            raise Exception('Event ID is missing after creation')
        await self._setup_kafka_infrastructure(
            event_id=final_aggregate.event.id, seating_config=seating_config
        )

        # 6. 初始化 RocksDB 座位 - 直接使用 SeatInitializationService
        await self._initialize_rocksdb_seats_direct(
            event_id=final_aggregate.event.id, tickets=final_aggregate.tickets
        )

        await self.session.commit()

        Logger.base.info(
            f'✅ Created event {final_aggregate.event.id} with {len(final_aggregate.tickets)} tickets'
        )

        return final_aggregate

    @Logger.io
    async def _setup_kafka_infrastructure(self, *, event_id: int, seating_config: Dict) -> None:
        """設置 Kafka 基礎設施"""
        try:
            Logger.base.info(f'🚀 Setting up Kafka infrastructure for event {event_id}')

            # 檢查 consumer 是否可用
            consumers_available = await self._check_consumer_availability()

            if not consumers_available:
                Logger.base.info('🔄 Consumers not available, attempting to start them...')
                startup_success = await self._auto_start_consumers(event_id)
                if startup_success:
                    Logger.base.info('✅ Consumers started successfully')
                else:
                    Logger.base.warning('⚠️ Failed to auto-start consumers')

            # 設置活動基礎設施
            infrastructure_success = await self.kafka_service.setup_event_infrastructure(
                event_id=event_id, seating_config=seating_config
            )

            if not infrastructure_success:
                Logger.base.warning(
                    f'⚠️ Infrastructure setup failed for event {event_id}, but continuing...'
                )

        except Exception as e:
            Logger.base.error(f'❌ Failed to setup Kafka infrastructure: {e}')
            # 不拋出異常，因為活動已經創建成功

    @Logger.io
    async def _initialize_rocksdb_seats_direct(self, *, event_id: int, tickets: list) -> None:
        """直接初始化 RocksDB 座位 - 使用簡單直接的方式"""
        try:
            Logger.base.info(
                f'💺 Directly initializing RocksDB seats for event {event_id} with {len(tickets)} tickets'
            )

            # 使用現有的 SeatInitializationService
            from src.seat_reservation.infra.seat_reservation_consumer import (
                SeatInitializationService,
            )

            seat_service = SeatInitializationService()
            initialized_count = await seat_service.initialize_seats_for_event(
                event_id=event_id, tickets=tickets
            )

            Logger.base.info(
                f'✅ Directly initialized {initialized_count}/{len(tickets)} seats in RocksDB'
            )

            # 驗證初始化結果
            await self._read_rocksdb_seats(event_id=event_id, sample_size=10)

        except Exception as e:
            Logger.base.error(f'❌ Failed to directly initialize RocksDB seats: {e}')

    @Logger.io
    async def _read_rocksdb_seats(self, *, event_id: int, sample_size: int = 10) -> None:
        """讀取 RocksDB 座位狀態進行驗證"""
        try:
            Logger.base.info(f'🔍 Reading RocksDB seats for event {event_id}')

            monitor = RocksDBMonitor()
            if not monitor.is_available():
                Logger.base.warning('⚠️ RocksDB monitor not available')
                return

            # 獲取座位狀態
            seats = monitor.get_all_seats(limit=sample_size)
            event_seats = [seat for seat in seats if seat.event_id == event_id]

            if event_seats:
                Logger.base.info(
                    f'📊 Found {len(event_seats)} seats in RocksDB for event {event_id}'
                )
                for seat in event_seats[:5]:  # 顯示前5個座位
                    Logger.base.info(
                        f'   🪑 Seat {seat.seat_id}: {seat.status}, Price: {seat.price}'
                    )

                # 獲取統計信息
                stats = monitor.get_event_statistics(event_id)
                if stats:
                    Logger.base.info(f'📈 Event {event_id} statistics:')
                    Logger.base.info(f'   Total seats: {stats.total_seats}')
                    Logger.base.info(f'   Available: {stats.available_seats}')
                    Logger.base.info(f'   Reserved: {stats.reserved_seats}')
                    Logger.base.info(f'   Sold: {stats.sold_seats}')
            else:
                Logger.base.warning(f'⚠️ No seats found in RocksDB for event {event_id}')

        except Exception as e:
            Logger.base.error(f'❌ Failed to read RocksDB seats: {e}')

    @Logger.io
    async def _check_consumer_availability(self) -> bool:
        """檢查必要的 consumer 是否運行"""
        try:
            # 根據日誌顯示的實際 consumer group 名稱更新
            required_groups = [
                'ticketing-system',  # 從日誌看到的實際 group 名稱之一
                'seat-reservation-service',  # 從日誌看到的實際 group 名稱
            ]

            active_groups = await self.kafka_service.get_active_consumer_groups()
            Logger.base.info(f'📋 Active consumer groups: {active_groups}')

            missing_groups = []
            for group in required_groups:
                # 檢查是否有包含該關鍵字的 group（因為實際名稱可能包含隨機後綴）
                group_found = any(group in active_group for active_group in active_groups)
                if not group_found:
                    missing_groups.append(group)
                    Logger.base.warning(
                        f"⚠️ Consumer group pattern '{group}' not found in active groups"
                    )

            if missing_groups:
                Logger.base.warning(f'⚠️ Missing consumer groups: {missing_groups}')
                return False

            Logger.base.info('✅ All required consumers are active')
            return True

        except Exception as e:
            Logger.base.warning(f'⚠️ Failed to check consumer status: {e}')
            return False

    async def _auto_start_consumers(self, event_id: int) -> bool:
        """自動啟動 consumers"""
        try:
            project_root = BASE_DIR

            consumers = [
                ('booking_mq_consumer', 'src.booking.infra.booking_mq_consumer'),
                (
                    'seat_reservation_consumer_1',
                    'src.seat_reservation.infra.seat_reservation_consumer',
                ),
                (
                    'seat_reservation_consumer_2',
                    'src.seat_reservation.infra.seat_reservation_consumer',
                ),
                (
                    'event_ticketing_mq_consumer',
                    'src.event_ticketing.infra.event_ticketing_mq_consumer',
                ),
            ]

            processes = []
            for name, module in consumers:
                try:
                    env = os.environ.copy()
                    env['EVENT_ID'] = str(event_id)
                    env['PYTHONPATH'] = str(project_root)

                    cmd = ['uv', 'run', 'python', '-m', module]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        cwd=project_root,
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )

                    processes.append((name, process))
                    Logger.base.info(f'✅ Started {name} (PID: {process.pid})')

                except Exception as e:
                    Logger.base.error(f'❌ Failed to start {name}: {e}')
                    return False

            # 等待 consumers 初始化
            await asyncio.sleep(3)

            # 驗證 consumers 是否真的啟動了
            return await self._check_consumer_availability()

        except Exception as e:
            Logger.base.error(f'❌ Auto-start consumers failed: {e}')
            return False
