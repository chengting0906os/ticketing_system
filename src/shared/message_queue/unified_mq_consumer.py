"""
統一的 MQ 消費者 (Unified MQ Consumer)

【最小可行原則 MVP】
- 這是什麼：從訊息佇列接收事件並路由到對應處理器的統一接口
- 為什麼需要：避免重複的消費者代碼，統一事件處理邏輯
- 核心概念：消費者模式 + 事件路由 + 處理器註冊
- 使用場景：booking服務接收ticketing服務的回應事件
"""

import asyncio
import base64
import queue
import threading
from typing import Any, Dict, List, Optional

from google.protobuf.json_format import MessageToDict
import orjson
from quixstreams import Application

from src.shared.config.core_setting import settings
from src.shared.logging.loguru_io import Logger


class UnifiedEventConsumer:
    """
    統一的事件消費者 (Quix Streams 版本)

    【Quix Streams 優勢】
    1. 簡化的 API，減少樣板代碼
    2. 內建異步支持和錯誤處理
    3. 自動 offset 管理和重試機制
    4. 更好的性能和資源管理
    """

    @Logger.io
    def __init__(
        self,
        topics: List[str],
        consumer_group_id: str = 'ticketing-system',
        consumer_tag: str = '[CONSUMER]',
        assigned_partitions: Optional[List[int]] = None,
    ):
        """
        初始化統一事件消費者

        Args:
            topics: 要訂閱的Kafka主題列表
            consumer_group_id: Kafka消費者組ID (直接使用，不再加UUID後綴)
            consumer_tag: 消費者標識，用於日誌追蹤
            assigned_partitions: 指定partition
        """

        self.topics = topics
        self.consumer_group_id = consumer_group_id
        self.consumer_tag = consumer_tag
        self.assigned_partitions = assigned_partitions
        self.running = False
        self.handlers: List[Any] = []

        # 新架構：消息隊列和異步處理器
        self.message_queue = queue.Queue()
        self.worker_task = None

        # 直接使用提供的 consumer_group_id，不再添加 UUID 後綴
        Logger.base.info(f'\033[93m🔧 [CONSUMER] Using Consumer Group: {consumer_group_id}\033[0m')

        self.app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=consumer_group_id,  # 直接使用原始 consumer_group_id
            auto_offset_reset='latest',
            processing_guarantee='exactly-once',
            consumer_extra_config={
                'enable.auto.commit': True,
                'auto.commit.interval.ms': 1000,
                'session.timeout.ms': 30000,
                'heartbeat.interval.ms': 10000,
            },
        )

    @Logger.io
    def register_handler(self, handler: Any) -> None:
        """註冊事件處理器"""
        self.handlers.append(handler)

    @Logger.io
    async def start(self):
        """
        啟動 Quix Streams 消費者 (純 Protobuf 版本)

        【Protobuf 流程】
        1. 創建 Protobuf topics 和 streaming dataframe
        2. 設置自動反序列化流水線
        3. 運行 streaming application
        """
        try:
            from quixstreams.models.serializers.protobuf import ProtobufDeserializer

            import src.shared.message_queue.proto.domain_event_pb2 as domain_event_pb2

            # Protobuf class with type stub support
            DomainEventProtoBufClass = domain_event_pb2.MqDomainEvent

            # 為每個 topic 創建 Protobuf topic 對象
            quix_topics = []
            for topic_name in self.topics:
                topic = self.app.topic(
                    name=topic_name,
                    value_deserializer=ProtobufDeserializer(
                        msg_type=DomainEventProtoBufClass,
                        to_dict=False,  # 保持 Protobuf 對象格式 # 請勿更動
                    ),
                    key_deserializer='str',
                )
                quix_topics.append(topic)

            # 為每個 topic 創建 streaming dataframe
            Logger.base.info(f'🔗 [CONSUMER] 設置 topic 監聽: {[t.name for t in quix_topics]}')

            for i, topic in enumerate(quix_topics):
                Logger.base.info(f'🔗 [CONSUMER] 處理 topic {i}: {topic.name}')
                topic_sdf = self.app.dataframe(topic=topic)
                topic_sdf = topic_sdf.apply(self._deserialize_message)  # 轉換為字典
                topic_sdf = topic_sdf.apply(self._log_before_filter)  # 記錄過濾前的數據
                topic_sdf = topic_sdf.filter(
                    lambda x: x.get('event_type') is not None
                )  # 過濾有效事件
                topic_sdf = topic_sdf.apply(self._collect_message_sync)

            Logger.base.info(f'✅ [CONSUMER] 監聽所有 topics: {self.topics}')

            self.running = True
            Logger.base.info(
                f'{self.consumer_tag} Quix Streams Consumer started for topics: {self.topics}'
            )

            # 在後台線程啟動異步消息處理器

            def start_worker():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_message_worker())

            worker_thread = threading.Thread(target=start_worker, daemon=True)
            worker_thread.start()
            Logger.base.info('🚀 [WORKER] 異步處理器已在後台線程啟動')

            self.app.run()

        except Exception as e:
            Logger.base.error(f'{self.consumer_tag} Failed to start Quix Streams Consumer: {e}')
            raise

    @Logger.io
    async def stop(self):
        """停止 Quix Streams 消費者"""
        self.running = False

        # 停止異步處理器
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task  # pyright: ignore[reportGeneralTypeIssues]
            except asyncio.CancelledError:
                pass

        # Quix Streams 會自動處理資源清理
        Logger.base.info(f'{self.consumer_tag} Quix Streams Consumer stopped')

    def _deserialize_message(self, message) -> Dict[str, Any]:
        """
        反序列化 Protobuf 消息 (Quix Streams 版本) - 支援混合格式

        【健壯的反序列化策略】
        1. 首先嘗試 Protobuf 對象處理
        2. 處理 Protobuf 中的 data 字段 (使用 orjson 反序列化)
        3. 所有失敗則跳過該消息避免阻塞
        """

        try:
            Logger.base.info(f'🔍 [CONSUMER] 收到消息進行反序列化: {type(message)}')

            # Step 1: 取出 value
            raw_value = message.value if hasattr(message, 'value') else message

            # Step 2: 嘗試 Protobuf
            try:
                event_data = MessageToDict(
                    raw_value,
                    preserving_proto_field_name=True,  # 保留原始字段名
                )
                Logger.base.info(f'🎉 [CONSUMER] Protobuf 反序列化完成: {event_data}')

                # Step 3: 處理 Protobuf 中的 data 字段 (使用 orjson 反序列化)
                if 'data' in event_data and event_data['data']:
                    data_bytes = base64.b64decode(
                        event_data['data']
                    )  # data 字段是 base64 編碼的 bytes，需要先解碼再用 orjson 解析
                    parsed_data = orjson.loads(data_bytes)
                    event_data['data'] = parsed_data
                    Logger.base.info(f'✅ [CONSUMER] orjson 反序列化 data 字段成功: {parsed_data}')

                return event_data
            except Exception as e:
                Logger.base.critical(f'⚠️ Protobuf 反序列化失敗: {e}')
                Logger.base.critical(f'Unrecognized message format: {type(raw_value)}, skipping...')
                return {'event_type': None, 'error': 'Unrecognized message format'}

        except Exception as e:
            Logger.base.error(f'Critical deserialization error: {e}')
            return {'event_type': None, 'error': str(e)}

    def _log_before_filter(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        Logger.base.info(f'🔍 [CONSUMER] 過濾前檢查: {event_data}')
        return event_data

    def _collect_message_sync(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步收集消息到隊列 - Quix Streams 專用"""
        try:
            # 只做簡單的消息收集，不處理業務邏輯
            self.message_queue.put(event_data)
            Logger.base.info(f'📨 [CONSUMER] 消息已收集到隊列: {event_data.get("event_type")}')
            return {'status': 'collected', 'event_type': event_data.get('event_type')}
        except Exception as e:
            Logger.base.error(f'❌ [CONSUMER] 消息收集失敗: {e}')
            return {'status': 'collection_failed', 'error': str(e)}

    @Logger.io
    async def _async_message_worker(self):
        """異步消息處理器 - 獨立於 Quix Streams"""
        Logger.base.info('🚀 [WORKER] 異步消息處理器啟動')

        while self.running:
            try:
                # 非阻塞方式從隊列取消息
                if not self.message_queue.empty():
                    event_data = self.message_queue.get_nowait()
                    await self._process_message_async(event_data)
                else:
                    # 沒有消息時短暫等待
                    await asyncio.sleep(0.1)
            except queue.Empty:
                await asyncio.sleep(0.1)
            except Exception as e:
                Logger.base.error(f'❌ [WORKER] 異步處理器錯誤: {e}')
                await asyncio.sleep(1)

    @Logger.io
    async def _process_message_async(self, event_data: Dict[str, Any]):
        """真正的異步消息處理 - 業務邏輯在這裡"""
        event_type = event_data.get('event_type')
        Logger.base.info(f'🚀 [WORKER] 處理事件: {event_type}')

        # 調用原本的異步 handlers
        for handler in self.handlers:
            try:
                Logger.base.info(f'🔍 [WORKER] 嘗試處理器: {type(handler).__name__}')

                # 直接 await async handler
                result = await handler.handle(event_data)

                if result:
                    Logger.base.info(f'✅ [WORKER] 處理成功: {type(handler).__name__}')
                    return

            except Exception as e:
                Logger.base.info(f'⚠️ [WORKER] 處理器 {type(handler).__name__} 跳過: {e}')
                continue

        Logger.base.warning(f'⚠️ [WORKER] 沒有處理器能處理事件: {event_type}')

    async def _process_event_with_handlers(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        處理事件與處理器路由 (純異步版本)

        【最小可行原則】
        1. 判斷事件類型
        2. 找到對應的 handler
        3. 直接分發處理
        4. 返回結果
        """
        event_type = event_data.get('event_type')
        Logger.base.info(f'🚀 [CONSUMER] 開始處理事件: {event_type}')
        Logger.base.info(f'🔍 [CONSUMER] 已註冊的處理器數量: {len(self.handlers)}')

        try:
            # 1. 快速路由到正確的 handler
            target_handler = None
            for i, handler in enumerate(self.handlers):
                handler_name = type(handler).__name__
                Logger.base.info(f'🔍 [CONSUMER] 檢查處理器 {i}: {handler_name}')
                try:
                    # 直接調用 async 方法
                    can_handle = await handler.can_handle(event_type or '')
                    Logger.base.info(
                        f'🔍 [CONSUMER] {handler_name}.can_handle("{event_type}") = {can_handle}'
                    )
                    if can_handle:
                        target_handler = handler
                        Logger.base.info(f'✅ [CONSUMER] 找到處理器: {handler_name}')
                        break
                except Exception as e:
                    Logger.base.error(f'❌ [CONSUMER] 檢查處理器 {handler_name} 時出錯: {e}')
                    continue

            # 2. 如果沒找到 handler，直接返回
            if not target_handler:
                Logger.base.warning(f'⚠️ [CONSUMER] 沒有找到處理器對應事件類型: {event_type}')
                return {'status': 'no_handler', 'event_type': event_type}

            # 3. 直接分發到 handler 處理
            Logger.base.info(f'🎯 [CONSUMER] 分發到 handler: {type(target_handler).__name__}')

            # 直接調用 async 方法
            result = await target_handler.handle(event_data)

            Logger.base.info(f'✅ [CONSUMER] 處理完成: {result}')
            return {'status': 'processed', 'result': result, 'event_type': event_type}

        except Exception as e:
            Logger.base.error(f'💥 [CONSUMER] 處理事件失敗: {e}')
            return {'status': 'error', 'error': str(e), 'event_type': event_type}
