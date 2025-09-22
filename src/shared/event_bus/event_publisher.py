"""
領域事件發布器 (Domain Event Publisher)

【最小可行原則 MVP】
- 這是什麼：將領域事件發送到Kafka的統一接口
- 為什麼需要：實現事件驅動架構，讓不同服務能異步通信
- 核心概念：發布者模式 + 事件序列化 + Kafka傳輸
- 使用場景：booking創建後通知ticketing服務
"""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime
import json
from typing import Dict, List, Optional, Protocol, runtime_checkable

import attrs
from kafka import KafkaProducer
from kafka.errors import KafkaError
import msgpack

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
    ) -> None:
        pass

    @abstractmethod
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> None:
        pass


class EventSerializer:
    @staticmethod
    def _extract_event_attributes(event: DomainEvent) -> dict:
        try:
            return attrs.asdict(event)
        except ImportError:
            pass
        except Exception:
            pass

        if hasattr(event, '__dict__'):
            return event.__dict__.copy()

        try:
            return vars(event).copy()
        except TypeError:
            return {}

    @staticmethod
    def _build_event_dict(event: DomainEvent, use_timestamp: bool = False) -> dict:
        """
        構建標準化的事件字典結構

        【MVP結構】統一格式確保所有消費者都能理解：
        {
            "event_type": "BookingCreated",     # 事件類型
            "aggregate_id": 123,                # 業務ID
            "occurred_at": "2024-01-01T10:00:00", # 時間
            "data": { ... }                     # 其他業務數據
        }
        """
        event_dict = {
            'event_type': event.__class__.__name__,  # 類名作為事件類型
            'aggregate_id': event.aggregate_id,  # 業務實體ID
            'occurred_at': event.occurred_at.timestamp()  # 時間格式化
            if use_timestamp
            else event.occurred_at.isoformat(),
            'data': {},  # 存放其他業務數據
        }

        # 提取所有屬性
        attributes = EventSerializer._extract_event_attributes(event)

        # 將非核心屬性放入data段
        for key, value in attributes.items():
            if key not in ['aggregate_id', 'occurred_at']:  # 避免重複
                if isinstance(value, datetime):
                    # 統一處理時間格式
                    event_dict['data'][key] = (
                        value.timestamp() if use_timestamp else value.isoformat()
                    )
                else:
                    event_dict['data'][key] = value

        return event_dict

    @staticmethod
    def serialize_json(event: DomainEvent) -> bytes:
        """
        序列化為JSON格式

        【使用場景】調試、日誌、人類可讀
        """
        event_dict = EventSerializer._build_event_dict(event, use_timestamp=False)
        return json.dumps(event_dict).encode('utf-8')

    @staticmethod
    def serialize_msgpack(event: DomainEvent) -> bytes:
        """
        序列化為MessagePack格式

        【使用場景】生產環境、高性能、節省帶寬
        比JSON小30-50%，解析速度快2-5倍
        """
        event_dict = EventSerializer._build_event_dict(event, use_timestamp=True)
        packed_data = msgpack.packb(event_dict)
        if not isinstance(packed_data, bytes):
            raise TypeError('MessagePack serialization did not return bytes')
        return packed_data


class KafkaEventPublisher(EventPublisher):
    """
    Kafka事件發布器實現

    【MVP核心功能】
    1. 連接Kafka集群
    2. 序列化事件數據（統一使用MessagePack）
    3. 發送到指定topic
    4. 確保消息送達
    """

    def __init__(self):
        """
        初始化Kafka發布器

        【MVP簡化】統一使用MessagePack，無需選擇
        - 體積小30-50%
        - 解析速度快2-5倍
        - 調試時可以用日誌查看事件內容
        """
        self.serializer = EventSerializer()
        self._producer: Optional[KafkaProducer] = None  # 延遲初始化
        self._lock = asyncio.Lock()  # 防止併發初始化

    @Logger.io
    async def _get_producer(self) -> KafkaProducer:
        """
        獲取或創建Kafka生產者（懶加載模式）

        【MVP原則】只在真正需要時才連接Kafka，節省資源
        """
        if self._producer is None:
            async with self._lock:  # 確保線程安全
                if self._producer is None:  # 雙重檢查
                    try:
                        producer_config = getattr(settings, 'KAFKA_PRODUCER_CONFIG', {})
                        self._producer = KafkaProducer(
                            **producer_config,
                            value_serializer=None,  # 我們自己處理序列化
                            key_serializer=lambda x: str(x).encode('utf-8') if x else None,
                        )
                        Logger.base.info('Kafka producer initialized successfully')
                    except Exception as e:
                        Logger.base.error(f'Failed to initialize Kafka producer: {e}')
                        raise
        return self._producer

    @Logger.io
    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> None:
        """
        發布單個事件到Kafka

        【MVP流程】
        1. 獲取生產者連接
        2. 序列化事件數據
        3. 發送到Kafka topic
        4. 等待確認回執

        Args:
            event: 要發布的領域事件
            topic: Kafka主題名（如"ticketing-booking-request"）
            partition_key: 分區鍵（決定消息路由到哪個分區）
        """
        producer = await self._get_producer()

        # 統一使用MessagePack序列化（高效且緊湊）
        value = self.serializer.serialize_msgpack(event)

        # 分區鍵：優先使用自定義，否則用aggregate_id
        key = partition_key or str(event.aggregate_id)

        try:
            # 發送到Kafka（異步包裝同步producer）
            future = producer.send(
                topic=topic,
                value=value,  # 消息體
                key=key,  # 分區鍵
                headers=[  # 消息頭，方便消費者識別
                    ('event_type', event.__class__.__name__.encode('utf-8')),
                    ('content_type', b'application/msgpack'),  # 統一使用MessagePack
                ],
            )

            # 等待發送確認（最多10秒）
            await asyncio.get_event_loop().run_in_executor(
                None,
                future.get,
                10,  # 超時時間
            )

            Logger.base.info(f'Published event {event.__class__.__name__} to {topic}')

        except KafkaError as e:
            Logger.base.error(f'Failed to publish event: {e}')
            raise

    @Logger.io
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> None:
        """
        批量發布多個事件（性能優化）

        【MVP原則】當需要發送多個事件時，批量操作更高效：
        - 減少網絡往返
        - 提高吞吐量
        - 降低延遲

        使用場景：一個操作產生多個事件時
        """
        if not events:
            return

        producer = await self._get_producer()
        futures = []  # 收集所有發送的future

        # 批量準備所有消息
        for event in events:
            # 統一使用MessagePack序列化（高效且緊湊）
            value = self.serializer.serialize_msgpack(event)

            # 分區鍵策略
            key = partition_key or str(event.aggregate_id)

            # 發送消息（不等待，收集future）
            future = producer.send(
                topic=topic,
                value=value,
                key=key,
                headers=[
                    ('event_type', event.__class__.__name__.encode('utf-8')),
                    ('content_type', b'application/msgpack'),  # 統一使用MessagePack
                ],
            )
            futures.append(future)

        try:
            # 等待所有消息發送完成
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: [f.get(10) for f in futures]
            )

            Logger.base.info(f'Published {len(events)} events to {topic}')

        except KafkaError as e:
            Logger.base.error(f'Failed to publish batch: {e}')
            raise

    @Logger.io
    async def close(self):
        """關閉Kafka生產者，釋放資源"""
        if self._producer:
            await asyncio.get_event_loop().run_in_executor(None, self._producer.close)
            self._producer = None


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
    ) -> None:
        """將事件存儲在內存中"""
        if topic not in self.published_events:
            self.published_events[topic] = []
        self.published_events[topic].append(event)
        Logger.base.debug(
            f'[TEST] Published event {event.__class__.__name__} to {topic} (key: {partition_key})'
        )

    @Logger.io
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> None:
        """批量存儲事件在內存中"""
        if topic not in self.published_events:
            self.published_events[topic] = []
        self.published_events[topic].extend(events)
        Logger.base.debug(
            f'[TEST] Published {len(events)} events to {topic} (key: {partition_key})'
        )

    def get_events(self, *, topic: str) -> List[DomainEvent]:
        """獲取指定topic的所有事件（測試用）"""
        return self.published_events.get(topic, [])

    def clear(self):
        """清除所有事件（測試清理用）"""
        self.published_events.clear()


class EventPublisherFactory:
    """
    事件發布器工廠

    【MVP工廠模式】根據環境自動選擇合適的發布器：
    - 生產環境：KafkaEventPublisher
    - 測試環境：InMemoryEventPublisher
    """

    @Logger.io
    @staticmethod
    def create_publisher(*, publisher_type: str = 'auto') -> EventPublisher:
        """
        創建事件發布器實例

        【MVP自動檢測】
        - auto: 根據環境自動選擇
        - kafka: 強制使用Kafka
        - memory: 強制使用內存（測試）

        【MVP簡化】統一使用MessagePack序列化，無需選擇格式
        """
        if publisher_type == 'auto':
            # 自動檢測：如果是調試模式且沒有Kafka配置，使用內存版本
            if settings.DEBUG and not getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', None):
                return InMemoryEventPublisher()
            else:
                return KafkaEventPublisher()
        elif publisher_type == 'kafka':
            return KafkaEventPublisher()
        elif publisher_type == 'memory':
            return InMemoryEventPublisher()
        else:
            raise ValueError(f'Unknown publisher type: {publisher_type}')


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
