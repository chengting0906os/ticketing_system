"""
動態Consumer管理器
實現按需創建和管理consumer的功能
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from src.shared.event_bus.unified_mq_consumer import UnifiedEventConsumer
from src.shared.logging.loguru_io import Logger


@dataclass
class ConsumerConfig:
    """Consumer配置"""

    topics: List[str]
    handler: Any
    assigned_partitions: Optional[List[int]] = None
    custom_group_id: Optional[str] = None


class DynamicConsumerManager:
    """
    動態Consumer管理器

    功能：
    1. 按需創建consumer
    2. 管理consumer生命週期
    3. 自動清理閒置consumer
    4. 支援partition指定
    """

    def __init__(self, max_consumers: int = 100):
        self.active_consumers: Dict[str, UnifiedEventConsumer] = {}
        self.consumer_tasks: Dict[str, asyncio.Task] = {}
        self.max_consumers = max_consumers
        self.executor = ThreadPoolExecutor(max_workers=10)

    @Logger.io
    async def create_consumer_for_request(
        self,
        request_id: str,
        config: ConsumerConfig,
        auto_cleanup_seconds: Optional[int] = 300,  # 5分鐘後自動清理
    ) -> str:
        """
        為特定請求創建專用consumer

        Args:
            request_id: 請求唯一標識
            config: Consumer配置
            auto_cleanup_seconds: 自動清理時間（秒）

        Returns:
            consumer_id: 創建的consumer ID
        """

        # 檢查consumer數量限制
        if len(self.active_consumers) >= self.max_consumers:
            await self._cleanup_oldest_consumer()

        # 生成唯一的consumer ID
        consumer_id = f'req-{request_id}-{uuid.uuid4().hex[:8]}'

        # 生成唯一的consumer group
        if config.custom_group_id:
            group_id = f'{config.custom_group_id}-{consumer_id}'
        else:
            group_id = f'dynamic-{consumer_id}'

        Logger.base.info(f'🚀 [DYNAMIC] 為請求 {request_id} 創建 consumer: {consumer_id}')
        Logger.base.info(f'📋 [DYNAMIC] Consumer group: {group_id}')

        # 創建consumer
        consumer = UnifiedEventConsumer(
            topics=config.topics,
            consumer_group_id=group_id,
            consumer_tag=f'[DYNAMIC-{consumer_id}]',
            assigned_partitions=config.assigned_partitions,
        )

        # 註冊處理器
        consumer.register_handler(config.handler)

        # 保存consumer
        self.active_consumers[consumer_id] = consumer

        # 啟動consumer
        task = asyncio.create_task(self._run_consumer(consumer_id, consumer))
        self.consumer_tasks[consumer_id] = task

        # 設置自動清理
        if auto_cleanup_seconds:
            asyncio.create_task(self._schedule_cleanup(consumer_id, auto_cleanup_seconds))

        return consumer_id

    @Logger.io
    async def create_partition_specific_consumer(
        self,
        partition_id: int,
        topics: List[str],
        handler: Any,
        request_context: Optional[str] = None,
    ) -> str:
        """
        創建專門處理特定partition的consumer

        Args:
            partition_id: 要處理的partition ID
            topics: topic列表
            handler: 事件處理器
            request_context: 請求上下文（可選）

        Returns:
            consumer_id: 創建的consumer ID
        """
        config = ConsumerConfig(
            topics=topics,
            handler=handler,
            assigned_partitions=[partition_id],
            custom_group_id=f'partition-{partition_id}',
        )

        request_id = request_context or f'partition-{partition_id}-{uuid.uuid4().hex[:6]}'

        return await self.create_consumer_for_request(
            request_id=request_id,
            config=config,
            auto_cleanup_seconds=600,  # partition consumer存活時間較長
        )

    @Logger.io
    async def create_user_session_consumer(
        self,
        user_id: int,
        session_id: str,
        topics: List[str],
        handler: Any,
    ) -> str:
        """
        為用戶會話創建專用consumer
        適用於需要用戶隔離的場景
        """
        config = ConsumerConfig(topics=topics, handler=handler, custom_group_id=f'user-{user_id}')

        request_id = f'session-{session_id}'

        return await self.create_consumer_for_request(
            request_id=request_id,
            config=config,
            auto_cleanup_seconds=1800,  # 30分鐘後清理
        )

    async def _run_consumer(self, consumer_id: str, consumer: UnifiedEventConsumer):
        """運行consumer"""
        try:
            Logger.base.info(f'▶️ [DYNAMIC] 啟動 consumer: {consumer_id}')
            await consumer.start()
        except Exception as e:
            Logger.base.error(f'❌ [DYNAMIC] Consumer {consumer_id} 運行錯誤: {e}')
        finally:
            Logger.base.info(f'⏹️ [DYNAMIC] Consumer {consumer_id} 已停止')

    async def _schedule_cleanup(self, consumer_id: str, delay_seconds: int):
        """排程清理consumer"""
        await asyncio.sleep(delay_seconds)
        await self.cleanup_consumer(consumer_id)

    @Logger.io
    async def cleanup_consumer(self, consumer_id: str):
        """清理指定的consumer"""
        if consumer_id not in self.active_consumers:
            return

        Logger.base.info(f'🧹 [DYNAMIC] 清理 consumer: {consumer_id}')

        # 停止consumer
        consumer = self.active_consumers[consumer_id]
        await consumer.stop()

        # 取消任務
        if consumer_id in self.consumer_tasks:
            task = self.consumer_tasks[consumer_id]
            if not task.done():
                task.cancel()
            del self.consumer_tasks[consumer_id]

        # 移除記錄
        del self.active_consumers[consumer_id]

        Logger.base.info(f'✅ [DYNAMIC] Consumer {consumer_id} 已清理')

    async def _cleanup_oldest_consumer(self):
        """清理最舊的consumer（當達到數量限制時）"""
        if not self.active_consumers:
            return

        oldest_id = next(iter(self.active_consumers))
        await self.cleanup_consumer(oldest_id)

    @Logger.io
    async def cleanup_all(self):
        """清理所有consumer"""
        Logger.base.info('🧹 [DYNAMIC] 清理所有動態 consumers')

        consumer_ids = list(self.active_consumers.keys())
        for consumer_id in consumer_ids:
            await self.cleanup_consumer(consumer_id)

    def get_active_consumer_count(self) -> int:
        """獲取活躍consumer數量"""
        return len(self.active_consumers)

    def get_consumer_info(self) -> Dict[str, Dict]:
        """獲取所有consumer的信息"""
        info = {}
        for consumer_id, consumer in self.active_consumers.items():
            info[consumer_id] = {
                'topics': consumer.topics,
                'group_id': consumer.consumer_group_id,
                'tag': consumer.consumer_tag,
                'assigned_partitions': getattr(consumer, 'assigned_partitions', None),
                'running': consumer.running,
            }
        return info


# 全局管理器實例
dynamic_consumer_manager = DynamicConsumerManager()


# 便利函數
async def create_request_consumer(
    request_id: str,
    topics: List[str],
    handler: Any,
    partition: Optional[int] = None,
    auto_cleanup_seconds: int = 300,
) -> str:
    """
    便利函數：為請求創建consumer

    使用範例：
    ```python
    # 為特定請求創建consumer
    consumer_id = await create_request_consumer(
        request_id="booking-123",
        topics=["booking-responses"],
        handler=my_handler,
        partition=0,  # 可選：指定partition
        auto_cleanup_seconds=300
    )
    ```
    """
    config = ConsumerConfig(
        topics=topics,
        handler=handler,
        assigned_partitions=[partition] if partition is not None else None,
    )

    return await dynamic_consumer_manager.create_consumer_for_request(
        request_id=request_id,
        config=config,
        auto_cleanup_seconds=auto_cleanup_seconds,
    )


async def create_partition_consumer(
    partition_id: int,
    topics: List[str],
    handler: Any,
    context: Optional[str] = None,
) -> str:
    """
    便利函數：創建partition專用consumer

    使用範例：
    ```python
    # A-1 group 只消費 partition 0
    consumer_id = await create_partition_consumer(
        partition_id=0,
        topics=["tickets"],
        handler=a1_handler,
        context="A-1-processing"
    )

    # A-2 group 只消費 partition 1
    consumer_id = await create_partition_consumer(
        partition_id=1,
        topics=["tickets"],
        handler=a2_handler,
        context="A-2-processing"
    )
    ```
    """
    return await dynamic_consumer_manager.create_partition_specific_consumer(
        partition_id=partition_id,
        topics=topics,
        handler=handler,
        request_context=context,
    )
