"""
統一的 MQ 發布器 (Unified MQ Publisher)

【最小可行原則 MVP】
- 這是什麼：將領域事件發送到訊息佇列的統一接口
- 為什麼需要：實現事件驅動架構，讓不同服務能異步通信
- 核心概念：發布者模式 + 事件序列化 + MQ傳輸
- 使用場景：booking創建後通知ticketing服務
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Protocol, runtime_checkable

import orjson
from quixstreams import Application
from quixstreams.models.serializers.protobuf import ProtobufDeserializer, ProtobufSerializer

from src.shared.config.core_setting import settings
from src.shared.logging.loguru_io import Logger


@runtime_checkable
class DomainEvent(Protocol):
    """
    領域事件協議定義

    【MVP原則】所有領域事件必須包含的最基本屬性：
    - aggregate_id: 業務實體ID（如booking_id）
    - occurred_at: 事件發生時間
    """

    @property
    def aggregate_id(self) -> int:
        """業務聚合根ID，用於分區和關聯"""
        ...

    @property
    def occurred_at(self) -> datetime:
        """事件發生時間戳"""
        ...


class EventPublisher(ABC):
    @abstractmethod
    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> bool:
        pass

    @abstractmethod
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> bool:
        pass


class ProtobufEventSerializer:
    """
    純 Protobuf 事件序列化器

    【高性能版本】
    - 移除 MessagePack 依賴
    - 直接使用 Protobuf 序列化
    - 更小的二進制體積和更快的序列化速度
    """

    @staticmethod
    def _extract_event_data(event: DomainEvent) -> dict:
        """提取事件的數據屬性"""
        if hasattr(event, '__dict__'):
            data = event.__dict__.copy()
        else:
            try:
                data = vars(event).copy()
            except TypeError:
                data = {}

        # 移除核心屬性，只保留業務數據
        data.pop('aggregate_id', None)
        data.pop('occurred_at', None)

        # 處理 datetime 對象和枚舉
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = int(value.timestamp())
            elif isinstance(value, Enum):  # 處理 Enum 類型
                data[key] = value.value

        return data


class QuixStreamEventPublisher(EventPublisher):
    """
    Quix Streams 事件發布器實現 (2024 最新版本 + Protobuf)

    【Quix Streams 優勢】
    1. 使用 Protobuf 序列化 (體積更小，性能更佳)
    2. Schema 驗證和向後兼容
    3. to_dict=False 提升性能
    4. 內建批處理優化，無需手動實現
    """

    def __init__(self):
        # 使用最新 Application 配置方式
        self.app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            processing_guarantee='exactly-once',  # 啟用 exactly-once 語義
            producer_extra_config={
                'enable.idempotence': settings.KAFKA_ENABLE_IDEMPOTENCE,
                'acks': settings.KAFKA_ACKS,
                'retries': settings.KAFKA_RETRIES,
                'compression.type': settings.KAFKA_COMPRESSION_TYPE,
                'batch.size': settings.KAFKA_BATCH_SIZE,  # Quix 內建批處理
                'linger.ms': settings.KAFKA_LINGER_MS,  # 自動批處理等待時間
                'delivery.timeout.ms': 30000,
                'request.timeout.ms': 10000,
            },
        )
        self._protobuf_available = self._check_protobuf_availability()
        self._topics = {}

    def _check_protobuf_availability(self) -> bool:
        """檢查 Protobuf 是否可用"""
        try:
            import src.shared.event_bus.proto.domain_event_pb2 as domain_event_pb2

            # Check DomainEvent class exists using getattr to avoid Pylance issues
            _ = getattr(domain_event_pb2, 'DomainEvent', None)
            if _ is None:
                raise ImportError('DomainEvent class not found in protobuf module')
            return True
        except ImportError:
            Logger.base.error('Protobuf schema not available. Please generate proto files.')
            raise ImportError('Protobuf serialization required but proto files not found')

    def _get_topic(self, topic_name: str):
        """獲取或創建 topic 對象 (純 Protobuf 序列化)"""
        if topic_name not in self._topics:
            import src.shared.event_bus.proto.domain_event_pb2 as domain_event_pb2

            # Protobuf class with type stub support
            DomainEventClass = domain_event_pb2.DomainEvent

            self._topics[topic_name] = self.app.topic(
                name=topic_name,
                value_serializer=ProtobufSerializer(msg_type=DomainEventClass),
                value_deserializer=ProtobufDeserializer(
                    msg_type=DomainEventClass,
                    to_dict=False,  # 保持 Protobuf 對象格式，提升性能
                ),
                key_serializer='str',
            )
            Logger.base.info(f'Using Protobuf serialization for topic: {topic_name}')

        return self._topics[topic_name]

    def _create_protobuf_event(self, event: DomainEvent):
        """創建 Protobuf 事件對象"""
        import src.shared.event_bus.proto.domain_event_pb2 as domain_event_pb2

        # Protobuf class with type stub support
        DomainEventClass = domain_event_pb2.DomainEvent

        proto_event = DomainEventClass()
        # event_id 在這裡是事件的唯一識別符，不是 BookingCreated 中的 event_id（活動 ID）
        # 生成唯一的事件 ID
        import uuid

        proto_event.event_id = str(uuid.uuid4())
        proto_event.event_type = event.__class__.__name__
        proto_event.aggregate_id = str(event.aggregate_id)
        proto_event.aggregate_type = getattr(event, 'aggregate_type', 'Booking')
        proto_event.occurred_at = int(event.occurred_at.timestamp())

        # 直接序列化事件數據為 bytes (僅在有額外數據時)
        event_data = ProtobufEventSerializer._extract_event_data(event)
        if event_data:
            # 使用 orjson 序列化 (orjson.dumps 直接返回 bytes)
            proto_event.data = orjson.dumps(event_data)

        return proto_event

    @Logger.io
    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> bool:
        """
        發布單個事件 (純 Protobuf 序列化)
        """
        kafka_topic = self._get_topic(topic)
        key = partition_key or str(event.aggregate_id)

        max_retries = 3
        retry_count = 0

        while retry_count <= max_retries:
            try:
                with self.app.get_producer() as producer:
                    # 創建 Protobuf 事件
                    proto_event = self._create_protobuf_event(event)

                    # 使用 Quix Streams 的 Protobuf 序列化
                    message = kafka_topic.serialize(
                        key=key,
                        value=proto_event,
                        headers={
                            'event_type': event.__class__.__name__,
                            'content_type': 'application/protobuf',
                        },
                    )

                    # 發送消息 - Quix 會自動批處理和優化
                    producer.produce(
                        topic=kafka_topic.name,
                        value=message.value,
                        key=message.key,
                        headers=message.headers,
                    )

                Logger.base.info(f'Published event {event.__class__.__name__} to {topic}')
                return True

            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    Logger.base.error(f'Failed to publish event after {max_retries} retries: {e}')
                    raise
                else:
                    wait_time = min(2**retry_count, 10)  # 指數退避，最大10秒
                    Logger.base.warning(
                        f'Publish attempt {retry_count} failed, retrying in {wait_time}s: {e}'
                    )
                    import time

                    time.sleep(wait_time)  # 使用同步 sleep 避免 loop 問題

        # 如果所有重試都失敗了，返回 False
        return False

    @Logger.io
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> bool:
        """
        批量發布事件 (利用 Quix Streams 內建批處理)
        """
        if not events:
            return True

        kafka_topic = self._get_topic(topic)

        try:
            with self.app.get_producer() as producer:
                # 批量創建和發送事件
                for event in events:
                    key = partition_key or str(event.aggregate_id)
                    proto_event = self._create_protobuf_event(event)

                    message = kafka_topic.serialize(
                        key=key,
                        value=proto_event,
                        headers={
                            'event_type': event.__class__.__name__,
                            'content_type': 'application/protobuf',
                        },
                    )

                    producer.produce(
                        topic=kafka_topic.name,
                        value=message.value,
                        key=message.key,
                        headers=message.headers,
                    )

                # 批量 flush 提升性能
                producer.flush(timeout=10.0)

            Logger.base.info(f'Published {len(events)} events to {topic} (batch processed)')
            return True
        except Exception as e:
            Logger.base.error(f'Failed to publish batch events: {e}')
            return False

    async def close(self):
        """清理資源"""
        self._topics.clear()


class InMemoryEventPublisher(EventPublisher):
    """
    內存事件發布器（測試專用）

    【MVP測試原則】
    - 不需要真實的Kafka環境
    - 可以檢查發布的事件
    - 測試時替換KafkaEventPublisher
    """

    def __init__(self):
        # 內存存儲：topic -> events列表
        self.published_events: Dict[str, List[DomainEvent]] = {}

    @Logger.io
    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> bool:
        """將事件存儲在內存中"""
        if topic not in self.published_events:
            self.published_events[topic] = []
        self.published_events[topic].append(event)
        Logger.base.debug(
            f'[TEST] Published event {event.__class__.__name__} to {topic} (key: {partition_key})'
        )
        return True

    @Logger.io
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> bool:
        """批量存儲事件在內存中"""
        if topic not in self.published_events:
            self.published_events[topic] = []
        self.published_events[topic].extend(events)
        Logger.base.debug(
            f'[TEST] Published {len(events)} events to {topic} (key: {partition_key})'
        )
        return True

    def get_events(self, *, topic: str) -> List[DomainEvent]:
        """獲取指定topic的所有事件（測試用）"""
        return self.published_events.get(topic, [])

    def clear(self):
        """清除所有事件（測試清理用）"""
        self.published_events.clear()


class EventPublisherFactory:
    """
    事件發布器工廠 (純 Quix Streams + Protobuf)

    【簡化版本】只支援：
    - quix: 使用 Quix Streams + Protobuf (預設)
    - memory: 內存版本 (測試用)
    """

    @Logger.io
    @staticmethod
    def create_publisher(*, publisher_type: str = 'auto') -> EventPublisher:
        """
        創建事件發布器實例

        【簡化選項】
        - auto: 根據環境自動選擇 (優先 Quix Streams)
        - quix: 強制使用 Quix Streams + Protobuf
        - memory: 強制使用內存 (測試)
        """
        if publisher_type == 'auto':
            # 自動檢測：優先使用 Quix Streams
            if settings.DEBUG and not getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', None):
                return InMemoryEventPublisher()
            else:
                return QuixStreamEventPublisher()
        elif publisher_type == 'quix':
            return QuixStreamEventPublisher()
        elif publisher_type == 'memory':
            return InMemoryEventPublisher()
        else:
            raise ValueError(
                f'Unsupported publisher type: {publisher_type}. Use: auto, quix, memory'
            )


# === 全局單例模式 ===
# 【MVP原則】整個應用使用同一個發布器實例，避免重複連接

_event_publisher: Optional[EventPublisher] = None


@Logger.io
def get_event_publisher() -> EventPublisher:
    """獲取全局事件發布器實例（單例模式）"""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisherFactory.create_publisher()
    return _event_publisher


@Logger.io
def set_event_publisher(publisher: EventPublisher) -> None:
    """設置自定義事件發布器（測試時有用）"""
    global _event_publisher
    _event_publisher = publisher


@Logger.io
def reset_event_publisher() -> None:
    """重置全局發布器實例（測試清理用）"""
    global _event_publisher
    if _event_publisher and hasattr(_event_publisher, 'close'):
        # 注意：這是同步的，未來考慮改為異步
        pass  # 現在只重置引用
    _event_publisher = None


@Logger.io
def _generate_default_topic(event: DomainEvent) -> str:
    """
    從事件類名生成默認topic名

    【MVP命名規則】
    BookingCreated -> ticketing.bookingcreated
    """
    event_type = event.__class__.__name__.replace('Event', '').lower()
    return f'ticketing.{event_type}'


# === 便捷函數 ===
# 【MVP使用接口】最常用的兩個函數
@Logger.io
async def publish_domain_event(
    event: DomainEvent, topic: Optional[str] = None, partition_key: Optional[str] = None
) -> None:
    """
    發布領域事件的便捷函數

    【MVP最常用】99%的場景都用這個函數：
    await publish_domain_event(
        event=BookingCreated(...),
        topic="ticketing-booking-request"
    )
    """
    if topic is None:
        topic = _generate_default_topic(event)

    publisher = get_event_publisher()
    await publisher.publish(event=event, topic=topic, partition_key=partition_key)


@Logger.io
async def publish_domain_events_batch(
    events: List[DomainEvent], topic: Optional[str] = None, partition_key: Optional[str] = None
) -> None:
    """
    批量發布領域事件的便捷函數

    【MVP批量場景】當一個業務操作產生多個事件時使用
    """
    if not events:
        return

    if topic is None:
        topic = _generate_default_topic(events[0])

    publisher = get_event_publisher()
    await publisher.publish_batch(events=events, topic=topic, partition_key=partition_key)
