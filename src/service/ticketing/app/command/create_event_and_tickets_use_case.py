"""
Create Event Use Case - 使用新的 EventTicketingAggregate

重構後的活動創建業務邏輯：
- 使用 EventTicketingAggregate 作為聚合根
- 整合活動和票務創建邏輯
- 負責 Kafka 基礎設施初始化
- 處理 Kvrocks 座位初始化
"""

import asyncio
import os
from typing import Dict

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from quixstreams import Application
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.config.core_setting import settings
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.constant.path import BASE_DIR
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
    PartitionKeyBuilder,
)
from src.platform.state.kvrocks_client import kvrocks_client_sync
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    IEventTicketingCommandRepo,
)
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate
from src.shared_kernel.app.interface.i_kafka_config_service import IKafkaConfigService
from src.shared_kernel.domain.enum.event_status import EventStatus


class CreateEventAndTicketsUseCase:
    def __init__(
        self,
        session: AsyncSession,
        event_ticketing_command_repo: IEventTicketingCommandRepo,
        kafka_service: IKafkaConfigService,
        init_state_handler: IInitEventAndTicketsStateHandler,
    ):
        self.session = session
        self.event_ticketing_command_repo = event_ticketing_command_repo
        self.kafka_service = kafka_service
        self.init_state_handler = init_state_handler

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        event_ticketing_command_repo: IEventTicketingCommandRepo = Depends(
            Provide[Container.event_ticketing_command_repo]
        ),
        kafka_service: IKafkaConfigService = Depends(Provide[Container.kafka_service]),
        init_state_handler: IInitEventAndTicketsStateHandler = Depends(
            Provide[Container.init_event_and_tickets_state_handler]
        ),
    ):
        return cls(
            session=session,
            event_ticketing_command_repo=event_ticketing_command_repo,
            kafka_service=kafka_service,
            init_state_handler=init_state_handler,
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

        # 5. 啟用活動 (DRAFT → AVAILABLE)
        # 需要從資料庫重新讀取 event 以確保它在 session 中被追蹤
        from sqlalchemy import select

        from src.service.ticketing.driven_adapter.model.event_model import EventModel

        stmt = select(EventModel).where(EventModel.id == final_aggregate.event.id)
        result = await self.session.execute(stmt)
        event_model = result.scalar_one()
        event_model.status = EventStatus.AVAILABLE.value

        if not final_aggregate.event.id:
            raise Exception('Event ID is missing after creation')
        await self._setup_kafka_infrastructure(
            event_id=final_aggregate.event.id, seating_config=seating_config
        )

        # 6. 啟動 seat_reservation consumer 並初始化座位
        await self._start_seat_reservation_consumer_and_initialize_seats(
            event_id=final_aggregate.event.id,
            ticket_tuples=ticket_tuples,
            seating_config=seating_config,
        )

        await self.session.commit()

        # 更新 aggregate 中的 status
        final_aggregate.event.status = EventStatus.AVAILABLE

        Logger.base.info(
            f'✅ Created event {final_aggregate.event.id} with {len(final_aggregate.tickets)} tickets'
        )

        return final_aggregate

    @Logger.io
    async def _setup_kafka_infrastructure(self, *, event_id: int, seating_config: Dict) -> None:
        """設置 Kafka 基礎設施"""
        try:
            Logger.base.info(f'🚀 Setting up Kafka infrastructure for event {event_id}')

            # 直接啟動 consumers（找不到就直接創）
            await self._auto_start_consumers(event_id)

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
    async def _start_seat_reservation_consumer_and_initialize_seats(
        self, *, event_id: int, ticket_tuples: list, seating_config: Dict
    ) -> None:
        """使用 InitEventAndTicketsStateHandler 初始化座位（分層架構）"""
        try:
            Logger.base.info(f'🚀 [CREATE-EVENT] Initializing seats for event {event_id}')

            # 調用 ticketing service 的 init_state_handler
            result = await self.init_state_handler.initialize_seats_from_config(
                event_id=event_id, seating_config=seating_config
            )

            if not result['success']:
                raise Exception(f'Seat initialization failed: {result["error"]}')

            Logger.base.info(
                f'✅ [CREATE-EVENT] Seat initialization completed: '
                f'{result["total_seats"]} seats, {result["sections_count"]} sections'
            )

        except Exception as e:
            Logger.base.error(f'❌ [CREATE-EVENT] Seat initialization error: {e}')
            raise

    @Logger.io
    async def _start_seat_reservation_consumer(self, *, event_id: int) -> None:
        """啟動特定事件的 seat_reservation consumer"""
        try:
            project_root = BASE_DIR
            env = os.environ.copy()
            env['EVENT_ID'] = str(event_id)
            env['PYTHONPATH'] = str(project_root)
            env['CONSUMER_GROUP_ID'] = KafkaConsumerGroupBuilder.seat_reservation_service(
                event_id=event_id
            )
            env['CONSUMER_INSTANCE_ID'] = '1'

            cmd = [
                'uv',
                'run',
                'python',
                '-m',
                'src.service.seat_reservation.driving_adapter.seat_reservation_mq_consumer',
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_root,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )

            Logger.base.info(
                f'✅ Started seat_reservation_mq_consumer (PID: {process.pid}) for event {event_id}'
            )

        except Exception as e:
            Logger.base.error(f'❌ Failed to start seat_reservation consumer: {e}')
            raise

    @Logger.io
    async def _send_seat_initialization_events(
        self, *, event_id: int, ticket_tuples: list, seating_config: Dict
    ) -> None:
        """發送座位初始化事件到 Kafka"""
        try:
            Logger.base.info(
                f'💺 Sending seat initialization events for event {event_id} with {len(ticket_tuples)} tickets'
            )

            # 1. 建立 section 配置映射 (section-subsection -> {rows, seats_per_row})
            section_config_map = {}
            for section in seating_config.get('sections', []):
                section_name = section['name']
                for subsection in section.get('subsections', []):
                    subsection_num = subsection['number']
                    rows = subsection['rows']
                    seats_per_row = subsection['seats_per_row']
                    section_id = f'{section_name}-{subsection_num}'
                    section_config_map[section_id] = {'rows': rows, 'seats_per_row': seats_per_row}

            # 2. 先寫入 subsection_total metadata 到 Kvrocks

            subsection_counts = {}
            for ticket_tuple in ticket_tuples:
                _, section, subsection, _, _, _, _ = ticket_tuple
                section_id = f'{section}-{subsection}'
                subsection_counts[section_id] = subsection_counts.get(section_id, 0) + 1

            client = kvrocks_client_sync.connect()
            for section_id, count in subsection_counts.items():
                key = f'subsection_total:{event_id}:{section_id}'
                client.set(key, count)
                Logger.base.info(f'📊 Set {key} = {count}')

            # 3. 發送座位初始化事件到 Kafka
            app = Application(
                broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
                producer_extra_config={
                    'enable.idempotence': True,
                    'acks': 'all',
                    'retries': 3,
                },
            )

            topic_name = KafkaTopicBuilder.seat_initialization_command_in_kvrocks(event_id=event_id)
            Logger.base.info(f'📡 Using seat initialization topic: {topic_name}')

            seat_init_topic = app.topic(
                name=topic_name,
                key_serializer='str',
                value_serializer='json',
            )

            initialized_count = 0

            with app.get_producer() as producer:
                for ticket_tuple in ticket_tuples:
                    try:
                        # ticket_tuple: (event_id, section, subsection, row, seat, price, status)
                        _, section, subsection, row, seat, price, _ = ticket_tuple
                        seat_id = f'{section}-{subsection}-{row}-{seat}'
                        section_id = f'{section}-{subsection}'

                        # 從配置映射中獲取 rows 和 seats_per_row
                        config = section_config_map.get(section_id, {})

                        # 創建座位初始化事件 (包含配置信息)
                        init_message = {
                            'action': 'INITIALIZE',
                            'seat_id': seat_id,
                            'event_id': event_id,
                            'price': price,
                            'section': section,
                            'subsection': subsection,
                            'row': row,
                            'seat': seat,
                            'rows': config.get('rows'),  # 新增：總行數
                            'seats_per_row': config.get('seats_per_row'),  # 新增：每行座位數
                        }

                        # 使用 section-based partition key，按字母順序分配：A→0, B→1, C→2...
                        # 這樣可以將不同 section 的負載分散到不同的 consumer instances
                        partition_number = ord(section[0]) - ord('A')
                        partition_key = PartitionKeyBuilder.section_based(
                            event_id=event_id, section=section, partition_number=partition_number
                        )

                        # 發送到 Kafka
                        message = seat_init_topic.serialize(key=partition_key, value=init_message)
                        producer.produce(
                            topic=seat_init_topic.name,
                            value=message.value,
                            key=message.key,
                        )

                        initialized_count += 1

                    except Exception as e:
                        try:
                            # ticket_tuple: (event_id, section, subsection, row, seat, price, status)
                            if len(ticket_tuple) >= 5:
                                _, section_name, subsection_num, row_num, seat_num = ticket_tuple[
                                    :5
                                ]
                                seat_identifier = (
                                    f'{section_name}-{subsection_num}-{row_num}-{seat_num}'
                                )
                            else:
                                seat_identifier = 'invalid_tuple'
                        except (ValueError, IndexError):
                            seat_identifier = 'unknown'
                        Logger.base.warning(
                            f'⚠️ Failed to send initialization for seat {seat_identifier}: {e}'
                        )
                        continue

                # 確保所有事件都發送完成
                producer.flush(timeout=10.0)

            Logger.base.info(
                f'✅ Sent {initialized_count}/{len(ticket_tuples)} seat initialization events to topic: {topic_name}'
            )

        except Exception as e:
            Logger.base.error(f'❌ Failed to send seat initialization events: {e}')

    @Logger.io
    async def _check_consumer_availability(
        self, *, event_id: int, max_retries: int = 3, retry_delay: float = 2.0
    ) -> bool:
        """檢查必要的 consumer 是否運行，包含重試機制"""
        try:
            # 1-1-2 配置的 consumer groups
            required_groups = KafkaConsumerGroupBuilder.get_all_consumer_groups(event_id=event_id)
            missing_groups = []

            for attempt in range(max_retries):
                active_groups = await self.kafka_service.get_active_consumer_groups()
                Logger.base.info(
                    f'📋 Active consumer groups (attempt {attempt + 1}): {active_groups}'
                )

                missing_groups = []
                for group in required_groups:
                    # 檢查是否有包含該關鍵字的 group（因為實際名稱可能包含隨機後綴）
                    group_found = any(group in active_group for active_group in active_groups)
                    if not group_found:
                        missing_groups.append(group)
                        Logger.base.warning(
                            f"⚠️ Consumer group pattern '{group}' not found in active groups"
                        )

                if not missing_groups:
                    Logger.base.info('✅ All required consumers are active')
                    return True

                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    Logger.base.info(
                        f'🔄 Retrying consumer verification in {retry_delay}s... (attempt {attempt + 1}/{max_retries})'
                    )
                    await asyncio.sleep(retry_delay)

            Logger.base.warning(
                f'⚠️ Missing consumer groups after {max_retries} attempts: {missing_groups}'
            )
            return False

        except Exception as e:
            Logger.base.warning(f'⚠️ Failed to check consumer status: {e}')
            return False

    async def _auto_start_consumers(self, event_id: int) -> None:
        """
        自動啟動 consumers - 1-2-1 配置

        架構配置：
        - booking: 1 consumer (輕量級訂單處理)
        - seat_reservation: 2 consumers (座位選擇算法 + Kvrocks 讀寫)
        - event_ticketing: 1 consumer (狀態管理)
        """
        try:
            project_root = BASE_DIR

            # Consumer 配置 (整合架構：PostgreSQL + Kvrocks)
            consumers = [
                # Ticketing Service - PostgreSQL 狀態管理 (Booking + Ticket)
                {
                    'name': 'ticketing_mq_consumer',
                    'module': 'src.service.ticketing.driving_adapter.mq_consumer.ticketing_mq_consumer',
                    'group_id': KafkaConsumerGroupBuilder.ticketing_service(event_id=event_id),
                    'instance_id': 1,
                },
                # Seat Reservation Service - Kvrocks 狀態管理
                {
                    'name': 'seat_reservation_mq_consumer',
                    'module': 'src.service.seat_reservation.driving_adapter.seat_reservation_mq_consumer',
                    'group_id': KafkaConsumerGroupBuilder.seat_reservation_service(
                        event_id=event_id
                    ),
                    'instance_id': 1,
                },
            ]

            processes = []
            for consumer_config in consumers:
                try:
                    env = os.environ.copy()
                    env['EVENT_ID'] = str(event_id)
                    env['PYTHONPATH'] = str(project_root)
                    env['CONSUMER_GROUP_ID'] = str(consumer_config['group_id'])
                    env['CONSUMER_INSTANCE_ID'] = str(consumer_config['instance_id'])

                    cmd = ['uv', 'run', 'python', '-m', str(consumer_config['module'])]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,  # type: ignore
                        cwd=project_root,
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )

                    processes.append((consumer_config['name'], process))
                    Logger.base.info(
                        f'✅ Started {consumer_config["name"]} '
                        f'(PID: {process.pid}, Group: {consumer_config["group_id"]})'
                    )

                except Exception as e:
                    Logger.base.error(f'❌ Failed to start {consumer_config["name"]}: {e}')

            # 短暫等待讓 consumers 啟動
            await asyncio.sleep(1)

            Logger.base.info(f'📊 [1-2-1 CONFIG] Total consumers started: {len(processes)}')

        except Exception as e:
            Logger.base.error(f'❌ Auto-start consumers failed: {e}')
