"""
統一的 Kafka 事件消費者 (Unified Event Consumer)

【最小可行原則 MVP】
- 這是什麼：從Kafka接收事件並路由到對應處理器的統一接口
- 為什麼需要：避免重複的消費者代碼，統一事件處理邏輯
- 核心概念：消費者模式 + 事件路由 + 處理器註冊
- 使用場景：booking服務接收ticketing服務的回應事件
"""

from abc import ABC, abstractmethod
import base64
from typing import Any, Dict, List, Optional

import anyio
from google.protobuf.json_format import MessageToDict
import orjson
from quixstreams import Application
import sniffio

from src.event_ticketing.port.event_ticketing_mq_gateway import (
    BookingCreatedCommand,
    EventTicketingMqGateway,
)
from src.shared.config.core_setting import settings
from src.shared.logging.loguru_io import Logger


class EventHandler(ABC):
    """
    事件處理器的抽象基類

    【MVP原則】所有事件處理器必須實現的兩個核心方法：
    1. can_handle: 判斷是否能處理某種事件類型
    2. handle: 實際處理事件的業務邏輯
    """

    @abstractmethod
    async def can_handle(self, event_type: str) -> bool:
        """
        檢查是否可以處理指定的事件類型

        【MVP路由原則】
        返回True表示這個處理器可以處理該事件類型
        例如：BookingEventHandler.can_handle("TicketsReserved") -> True
        """
        pass

    @abstractmethod
    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """
        處理事件的具體業務邏輯

        【MVP處理原則】
        接收反序列化後的事件數據，執行相應的業務操作
        返回True表示處理成功，False表示處理失敗
        例如：更新booking狀態、發送通知等
        """
        pass


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
    ):
        """
        初始化統一事件消費者

        Args:
            topics: 要訂閱的Kafka主題列表
            consumer_group_id: Kafka消費者組ID
            consumer_tag: 消費者標識，用於日誌追蹤
        """

        self.topics = topics
        self.consumer_group_id = consumer_group_id
        self.consumer_tag = consumer_tag
        self.running = False
        self.handlers: List[EventHandler] = []

        # 初始化 Quix Application（使用新的 Consumer Group ID 以重新處理消息）
        import uuid

        new_consumer_group = f'{consumer_group_id}-{uuid.uuid4().hex[:8]}'
        Logger.base.info(
            f'\033[93m🔄 [CONSUMER] 使用新的 Consumer Group: {new_consumer_group}\033[0m'
        )

        self.app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=new_consumer_group,
            auto_offset_reset='latest',  # 從最新消息開始，跳過有問題的舊消息
            processing_guarantee='exactly-once',  # 啟用 exactly-once 語義
            consumer_extra_config={
                'enable.auto.commit': True,
                'auto.commit.interval.ms': 1000,
                'session.timeout.ms': 30000,
                'heartbeat.interval.ms': 10000,
            },
        )

    @Logger.io
    def register_handler(self, handler: EventHandler) -> None:
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

            import src.shared.event_bus.proto.domain_event_pb2 as domain_event_pb2

            # Protobuf class with type stub support
            DomainEventProtoBufClass = domain_event_pb2.DomainEvent

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
                topic_sdf = topic_sdf.apply(self._process_event_with_handlers_sync)

            Logger.base.info(f'✅ [CONSUMER] 監聽所有 topics: {self.topics}')

            self.running = True
            Logger.base.info(
                f'{self.consumer_tag} Quix Streams Consumer started for topics: {self.topics}'
            )
            self.app.run()

        except Exception as e:
            Logger.base.error(f'{self.consumer_tag} Failed to start Quix Streams Consumer: {e}')
            raise

    @Logger.io
    async def stop(self):
        """停止 Quix Streams 消費者"""
        self.running = False
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

    def _run_async_safely(self, coro):
        """安全地在同步上下文中運行異步函數"""
        from concurrent.futures import ThreadPoolExecutor

        try:
            # 檢查是否在異步上下文中
            sniffio.current_async_library()

            # 如果在異步上下文中，使用 ThreadPoolExecutor 在新線程中運行
            def run_in_thread():
                async def wrapper():
                    return await coro

                return anyio.run(wrapper)

            with ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()

        except sniffio.AsyncLibraryNotFoundError:
            # 沒有運行的異步庫，直接使用 anyio.run
            async def wrapper():
                return await coro

            return anyio.run(wrapper)

    @Logger.io
    def _process_event_with_handlers_sync(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接同步處理事件 - 調用異步 gateway

        【最直接的解決方案】
        直接調用 gateway 的異步方法，用 anyio 執行
        """
        event_type = event_data.get('event_type')
        Logger.base.info(f'🚀 [CONSUMER] 處理事件: {event_type}')

        try:
            # 直接處理 BookingCreated 事件
            if event_type == 'BookingCreated':
                Logger.base.info('📨 [CONSUMER] 處理 BookingCreated 事件')

                # 找到 EventTicketingEventConsumer
                ticketing_handler = None
                for handler in self.handlers:
                    if type(handler).__name__ == 'EventTicketingEventConsumer':
                        ticketing_handler = handler
                        break

                if ticketing_handler:
                    Logger.base.info('✅ [CONSUMER] 找到 EventTicketingEventConsumer，開始處理')

                    # 從 handler 中獲取 gateway
                    gateway: EventTicketingMqGateway = ticketing_handler.event_ticketing_gateway
                    Logger.base.info(f'📡 [CONSUMER] 獲取到 」{gateway}')

                    # 創建命令

                    parsed_data = event_data if isinstance(event_data, dict) else {}
                    Logger.base.info(f'📋 [CONSUMER] 事件數據: {parsed_data}')
                    command = BookingCreatedCommand.from_event_data(event_data=parsed_data)
                    Logger.base.info(f'🎯 [CONSUMER] 處理預訂: booking_id={command.booking_id}')

                    # 直接調用 gateway 的異步方法

                    try:
                        # 調用 gateway.handle_booking_created (這個本來就是異步的)
                        Logger.base.info('🔥 [DEBUG] 準備調用 anyio')
                        Logger.base.info(f'🔥 [DEBUG] gateway 類型: {type(gateway)}')
                        Logger.base.info(f'🔥 [DEBUG] command 類型: {type(command)}')

                        result = self._run_async_safely(gateway.handle_booking_created(command))
                        Logger.base.info('🔥 [DEBUG] anyio 執行完成')
                        Logger.base.info(f'🚀 [CONSUMER] Gateway 處理結果: {result}')
                        Logger.base.info(f'🔥 [DEBUG] result 類型: {type(result)}')

                        # 根據結果發送回應
                        if result.is_success:
                            self._run_async_safely(gateway.send_success_response(result))
                            Logger.base.info(
                                f'✅ [CONSUMER] 處理成功: booking_id={command.booking_id}'
                            )

                            return {
                                'status': 'processed',
                                'event_type': event_type,
                                'booking_id': command.booking_id,
                                'ticket_ids': result.ticket_ids or [],
                            }
                        else:
                            self._run_async_safely(
                                gateway.send_failure_response(
                                    command.booking_id, result.error_message or 'Unknown error'
                                )
                            )
                            Logger.base.error(f'❌ [CONSUMER] 處理失敗: {result.error_message}')
                            return {
                                'status': 'error',
                                'error': result.error_message,
                                'event_type': event_type,
                            }

                    except Exception as e:
                        Logger.base.error(f'❌ [CONSUMER] Gateway 調用失敗: {e}')
                        return {'status': 'error', 'error': str(e), 'event_type': event_type}

                else:
                    Logger.base.error('❌ [CONSUMER] 找不到 EventTicketingEventConsumer')
                    return {'status': 'no_handler', 'event_type': event_type}

            # 處理其他事件類型
            else:
                Logger.base.info(f'📨 [CONSUMER] 其他事件類型: {event_type}')
                return {'status': 'unhandled', 'event_type': event_type}

        except Exception as e:
            Logger.base.error(f'💥 [CONSUMER] 處理事件失敗: {e}')
            import traceback

            Logger.base.error(f'💥 [CONSUMER] 詳細錯誤: {traceback.format_exc()}')
            return {'status': 'error', 'error': str(e), 'event_type': event_type}

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


# === 全局消費者管理 ===
# 【MVP原則】使用全局實例管理，避免重複創建消費者

_unified_consumer: Optional[UnifiedEventConsumer] = None


@Logger.io
async def start_unified_consumer(
    topics: List[str], handlers: List[EventHandler], consumer_tag: str = '[CONSUMER]'
) -> None:
    """
    啟動統一的事件消費者

    【MVP啟動接口】這是外部啟動消費者的統一入口

    Args:
        topics: 要監聽的Kafka主題列表
        handlers: 事件處理器列表（每個服務提供自己的處理器）
        consumer_tag: 消費者標識，用於日志追蹤

    使用例子：
    ```python
    topics = ["ticketing-booking-request", "ticketing-booking-response"]
    handlers = [BookingEventConsumer(), TicketingEventConsumer()]
    await start_unified_consumer(topics, handlers)
    ```
    """
    global _unified_consumer

    if _unified_consumer is None:
        # 創建統一消費者實例
        _unified_consumer = UnifiedEventConsumer(topics, consumer_tag=consumer_tag)

        # 註冊所有事件處理器
        for handler in handlers:
            _unified_consumer.register_handler(handler)

    # 啟動消費者
    await _unified_consumer.start()


@Logger.io
async def stop_unified_consumer() -> None:
    """
    停止統一的事件消費者

    【MVP停止接口】清理全局消費者資源
    """
    global _unified_consumer
    if _unified_consumer:
        await _unified_consumer.stop()
        _unified_consumer = None


@Logger.io
def get_unified_consumer() -> Optional[UnifiedEventConsumer]:
    """
    獲取統一的消費者實例

    【MVP查詢接口】用於監控和調試
    """
    global _unified_consumer
    return _unified_consumer
