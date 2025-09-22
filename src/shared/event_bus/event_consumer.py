"""
統一的 Kafka 事件消費者 (Unified Event Consumer)

【最小可行原則 MVP】
- 這是什麼：從Kafka接收事件並路由到對應處理器的統一接口
- 為什麼需要：避免重複的消費者代碼，統一事件處理邏輯
- 核心概念：消費者模式 + 事件路由 + 處理器註冊
- 使用場景：booking服務接收ticketing服務的回應事件
"""

from abc import ABC, abstractmethod
import asyncio
import json
from typing import Any, Dict, List, Optional

from kafka import KafkaConsumer
import msgpack

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
    async def handle(self, event_data: Dict[str, Any]) -> None:
        """
        處理事件的具體業務邏輯

        【MVP處理原則】
        接收反序列化後的事件數據，執行相應的業務操作
        例如：更新booking狀態、發送通知等
        """
        pass


class UnifiedEventConsumer:
    """
    統一的事件消費者

    【MVP核心職責】
    1. 連接Kafka並訂閱多個topics
    2. 消費消息並反序列化
    3. 根據事件類型路由到對應的處理器
    4. 處理錯誤和重試
    """

    @Logger.io
    def __init__(self, topics: List[str], consumer_group_id: str = 'ticketing-system'):
        """
        初始化統一事件消費者

        Args:
            topics: 要訂閱的Kafka主題列表
            consumer_group_id: Kafka消費者組ID（同組內的消費者會分攤消息）
        """
        self.topics = topics
        self.consumer_group_id = consumer_group_id
        self.consumer: Optional[KafkaConsumer] = None  # Kafka消費者實例
        self.running = False  # 運行狀態標誌
        self.handlers: List[EventHandler] = []  # 註冊的事件處理器列表

    @Logger.io
    def register_handler(self, handler: EventHandler) -> None:
        """
        註冊事件處理器

        【MVP註冊原則】
        每個服務可以註冊自己的處理器來處理相關事件
        例如：booking服務註冊BookingEventHandler
        """
        self.handlers.append(handler)

    @Logger.io
    async def start(self):
        """
        啟動Kafka消費者

        【MVP啟動流程】
        1. 配置Kafka消費者
        2. 訂閱指定的topics
        3. 開始消息消費循環
        """
        try:
            # 初始化消費者配置
            consumer_config = settings.KAFKA_CONSUMER_CONFIG.copy()
            consumer_config['group_id'] = self.consumer_group_id

            # 創建Kafka消費者，訂閱所有topics
            self.consumer = KafkaConsumer(
                *self.topics,  # 解包topics列表
                **consumer_config,  # type: ignore
                value_deserializer=None,  # 我們自己處理反序列化
            )

            self.running = True
            Logger.base.info(f'Unified Event Consumer started for topics: {self.topics}')

            # 開始消費消息的主循環
            await self._consume_messages()

        except Exception as e:
            Logger.base.error(f'Failed to start Unified Event Consumer: {e}')
            raise

    @Logger.io
    async def stop(self):
        """
        停止Kafka消費者

        【MVP停止流程】
        1. 設置停止標誌
        2. 關閉Kafka連接
        3. 清理資源
        """
        self.running = False
        if self.consumer:
            self.consumer.close()
        Logger.base.info('Unified Event Consumer stopped')

    @Logger.io
    async def _consume_messages(self):
        """
        消費消息的主循環

        【MVP消費循環】
        1. 輪詢Kafka獲取消息
        2. 批量處理消息
        3. 提交偏移量
        4. 錯誤處理和重試
        """
        while self.running:
            try:
                # 輪詢消息（非阻塞，100毫秒超時）
                message_batch = self.consumer.poll(timeout_ms=100)  # type: ignore

                if message_batch:
                    # 處理批次中的所有消息
                    for topic_partition, messages in message_batch.items():
                        Logger.base.critical(
                            f'Processing {len(messages)} messages from {topic_partition}'
                        )
                        for message in messages:
                            # 提取消息的關鍵部分，避免傳遞整個 ConsumerRecord 對象
                            try:
                                message_value = message.value
                                Logger.base.critical(
                                    f'Processing message with value type: {type(message_value)}'
                                )
                                await self._process_message_value(message_value)
                            except Exception as e:
                                Logger.base.error(f'Error processing individual message: {e}')
                                # 繼續處理其他消息

                    # 處理完成後提交偏移量（確認消費）
                    self.consumer.commit()  # type: ignore

                # 短暫休眠，避免CPU空轉
                await asyncio.sleep(0.01)

            except Exception as e:
                Logger.base.error(f'Error in consume loop: {e}')
                await asyncio.sleep(1)  # 出錯時等待重試  # 出錯時等待重試

    async def _process_message_value(self, message_value: bytes):
        """
        處理消息值，避免 ConsumerRecord 對象問題

        【MVP處理流程】
        1. 反序列化消息內容
        2. 提取事件類型
        3. 查找能處理該事件的處理器
        4. 執行事件處理邏輯
        """
        try:
            Logger.base.critical(
                f'Starting _process_message_value with value type: {type(message_value)}'
            )

            # 反序列化消息（支持MessagePack和JSON）
            Logger.base.critical(f'About to deserialize message value: {type(message_value)}')
            event_data = self._deserialize_message(message_value)
            Logger.base.critical(f'Deserialized event_data: {event_data}')

            event_type = event_data.get('event_type')
            Logger.base.critical(f'Extracted event_type: {event_type}')

            Logger.base.info(f'Processing event: {event_type}')

            # 路由到合適的處理器
            if event_type:
                handled = False
                Logger.base.critical(f'Looking for handlers, total handlers: {len(self.handlers)}')

                # 遍歷所有註冊的處理器
                for i, handler in enumerate(self.handlers):
                    Logger.base.critical(f'Checking handler {i}: {type(handler)}')

                    can_handle_result = await handler.can_handle(event_type)
                    Logger.base.critical(f'Handler {i} can_handle result: {can_handle_result}')

                    if can_handle_result:
                        Logger.base.critical(
                            f'Handler {i} will handle the event, calling handler.handle()'
                        )
                        await handler.handle(event_data)
                        Logger.base.critical(
                            f'Handler {i} finished handling the event successfully'
                        )
                        handled = True
                        break  # 找到處理器後停止查找

                if not handled:
                    Logger.base.warning(f'No handler found for event type: {event_type}')
                else:
                    Logger.base.critical(f'Event {event_type} was handled successfully')
            else:
                Logger.base.warning('Event type is missing in event data')

            Logger.base.critical('_process_message_value completed successfully')

        except Exception as e:
            Logger.base.error(f'Error processing message value: {e}')
            Logger.base.error(f'Error type: {type(e)}')
            import traceback

            Logger.base.error(f'Full traceback: {traceback.format_exc()}')

    def _deserialize_message(self, raw_value: bytes) -> Dict[str, Any]:
        """
        反序列化Kafka消息值

        【MVP反序列化策略】
        1. 優先嘗試MessagePack（生產環境常用，更高效）
        2. 回退到JSON（調試時常用，可讀性好）
        3. 失敗時拋出錯誤

        這與event_publisher的序列化策略對應
        """
        try:
            # 首先嘗試MessagePack格式
            return msgpack.unpackb(raw_value, raw=False)
        except Exception:
            try:
                # 回退到JSON格式
                return json.loads(raw_value.decode('utf-8'))
            except Exception as e:
                raise ValueError(f'Failed to deserialize message: {e}')


# === 全局消費者管理 ===
# 【MVP原則】使用全局實例管理，避免重複創建消費者

_unified_consumer: Optional[UnifiedEventConsumer] = None


@Logger.io
async def start_unified_consumer(topics: List[str], handlers: List[EventHandler]) -> None:
    """
    啟動統一的事件消費者

    【MVP啟動接口】這是外部啟動消費者的統一入口

    Args:
        topics: 要監聽的Kafka主題列表
        handlers: 事件處理器列表（每個服務提供自己的處理器）

    使用例子：
    ```python
    topics = ["ticketing-booking-request", "ticketing-booking-response"]
    handlers = [BookingEventHandler(), TicketingEventHandler()]
    await start_unified_consumer(topics, handlers)
    ```
    """
    global _unified_consumer

    if _unified_consumer is None:
        # 創建統一消費者實例
        _unified_consumer = UnifiedEventConsumer(topics)

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
