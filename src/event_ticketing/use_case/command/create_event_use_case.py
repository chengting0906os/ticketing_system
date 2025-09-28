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
from src.event_ticketing.domain.seat_initialization_event import SeatInitializationEvent
from src.shared.config.db_setting import get_async_session
from src.shared.config.di import Container
from src.shared.constant.path import BASE_DIR
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.shared.message_queue.unified_mq_publisher import publish_domain_event
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

        # 2. 保存聚合根（只保存 Event，獲得 ID）
        saved_aggregate = await self.event_ticketing_command_repo.create_event_aggregate(
            event_aggregate=event_aggregate
        )

        # 3. 生成票務（現在有 event.id 了）
        saved_aggregate.generate_tickets()

        # 4. 使用高效能批量創建票務
        # 由於票務數量很多，我們直接使用批量方法
        from src.event_ticketing.infra.event_ticketing_command_repo_impl import (
            EventTicketingCommandRepoImpl,
        )

        if isinstance(self.event_ticketing_command_repo, EventTicketingCommandRepoImpl):
            # 使用高效能批量保存方法重新保存整個聚合根
            final_aggregate = (
                await self.event_ticketing_command_repo.create_event_aggregate_with_batch_tickets(
                    event_aggregate=saved_aggregate
                )
            )
        else:
            # 使用標準方法
            final_aggregate = await self.event_ticketing_command_repo.update_event_aggregate(
                event_aggregate=saved_aggregate
            )

        # 5. 設置 Kafka 基礎設施
        if final_aggregate.event.id:
            await self._setup_kafka_infrastructure(
                event_id=final_aggregate.event.id, seating_config=seating_config
            )

            # 6. 初始化 RocksDB 座位
            await self._initialize_rocksdb_seats(
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
    async def _initialize_rocksdb_seats(self, *, event_id: int, tickets) -> None:
        """初始化 RocksDB 座位"""
        try:
            Logger.base.info(f'💺 Initializing RocksDB seats for event {event_id}')

            for ticket in tickets:
                try:
                    # 創建座位初始化事件
                    init_event = SeatInitializationEvent(
                        event_id=event_id,
                        seat_id=ticket.seat_identifier,
                        section=ticket.section,
                        subsection=ticket.subsection,
                        row=ticket.row,
                        seat=ticket.seat,
                        price=ticket.price,
                    )

                    # 獲取分區鍵
                    partition_key = self.kafka_service.get_partition_key_for_seat(
                        section=ticket.section,
                        subsection=ticket.subsection,
                        row=ticket.row,
                        seat=ticket.seat,
                        event_id=event_id,
                    )

                    # 發送初始化命令
                    topic_name = KafkaTopicBuilder.seat_initialization_command(event_id=event_id)
                    await publish_domain_event(
                        event=init_event, topic=topic_name, partition_key=partition_key
                    )

                except Exception as e:
                    Logger.base.warning(
                        f'⚠️ Failed to initialize seat {ticket.seat_identifier}: {e}'
                    )
                    # 繼續處理其他座位

            Logger.base.info(f'✅ RocksDB seat initialization commands sent for event {event_id}')

        except Exception as e:
            Logger.base.error(f'❌ Failed to initialize RocksDB seats: {e}')
            # 不拋出異常，因為活動已經創建成功

    @Logger.io
    async def _check_consumer_availability(self) -> bool:
        """檢查必要的 consumer 是否運行"""
        try:
            required_groups = [
                'booking-service-consumer',
                'seat-reservation-consumer',
                'event-ticketing-consumer',
            ]

            active_groups = await self.kafka_service.get_active_consumer_groups()

            for group in required_groups:
                if group not in active_groups:
                    Logger.base.warning(f"⚠️ Consumer group '{group}' is not active")
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
