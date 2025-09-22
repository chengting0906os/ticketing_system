"""
Ticketing Event Consumer (基礎設施層)

【最小可行原則 MVP】
- 這是什麼：Kafka 事件消費者，處理外部系統的技術細節
- 為什麼需要：實現 EventHandler 接口，橋接 Kafka 和業務邏輯
- 核心概念：Adapter 模式，將外部事件轉換為業務命令
- 使用場景：接收 Kafka 事件，調用 Gateway 處理業務邏輯
"""

import json
from typing import Any, Dict

from src.event_ticketing.port.event_ticketing_mq_gateway import (
    BookingCreatedCommand,
    EventTicketingMqGateway,
)
from src.shared.event_bus.event_consumer import EventHandler
from src.shared.logging.loguru_io import Logger


class EventTicketingEventConsumer(EventHandler):
    """
    Ticketing 事件消費者 (基礎設施層)

    【職責】
    1. 實現 EventHandler 接口
    2. 解析和驗證外部事件格式
    3. 轉換為業務命令
    4. 調用 Gateway 處理業務邏輯
    """

    def __init__(self, event_ticketing_gateway: EventTicketingMqGateway):
        """
        初始化 Ticketing 事件消費者

        Args:
            event_ticketing_gateway: 票務事件處理的業務邏輯接口
        """
        self.event_ticketing_gateway = event_ticketing_gateway

    async def can_handle(self, event_type: str) -> bool:
        """檢查是否可以處理指定的事件類型"""
        return event_type == 'BookingCreated'

    def _parse_event_data(self, event_data: Any) -> Dict[str, Any]:
        """
        強健的事件數據解析，處理多種可能的輸入格式

        Args:
            event_data: 可能是字典、字符串或其他格式的事件數據

        Returns:
            解析後的字典格式事件數據，解析失敗則返回空字典
        """
        try:
            # 如果已經是字典，直接返回
            if isinstance(event_data, dict):
                Logger.base.info(
                    f'📋 [TICKETING Consumer] 事件數據已是字典格式: {type(event_data)}'
                )
                return event_data

            # 如果是字符串，嘗試 JSON 解析
            elif isinstance(event_data, str):
                Logger.base.info(
                    f'🔄 [TICKETING Consumer] 嘗試解析字符串格式事件數據: {event_data[:100]}...'
                )
                parsed = json.loads(event_data)
                Logger.base.info('✅ [TICKETING Consumer] JSON 解析成功')
                return parsed

            # 其他類型，嘗試轉換為字符串再解析
            else:
                Logger.base.warning(f'⚠️ [TICKETING Consumer] 未知事件數據格式: {type(event_data)}')
                # 嘗試將對象轉換為字典（如果有 __dict__ 屬性）
                if hasattr(event_data, '__dict__'):
                    return vars(event_data)
                else:
                    Logger.base.error(
                        f'❌ [TICKETING Consumer] 無法解析事件數據格式: {type(event_data)}'
                    )
                    return {}

        except Exception as e:
            Logger.base.error(f'❌ [TICKETING Consumer] 事件數據解析失敗: {e}')
            return {}

    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """
        處理事件 (Adapter 職責)

        【最小可行原則】
        1. 解析事件數據
        2. 轉換為業務命令
        3. 調用 Gateway
        4. 返回結果
        """
        try:
            # 1. 解析事件數據
            parsed_event_data = self._parse_event_data(event_data)
            if not parsed_event_data:
                Logger.base.error('Failed to parse event data')
                return False

            event_type = parsed_event_data.get('event_type')
            Logger.base.info(f'📨 [TICKETING Consumer] 收到事件: {event_type}')

            # 2. 只處理 BookingCreated 事件
            if event_type != 'BookingCreated':
                Logger.base.warning(f'Unknown event type: {event_type}')
                return False

            # 3. 轉換為業務命令
            command = BookingCreatedCommand.from_event_data(parsed_event_data)
            Logger.base.info(f'🎯 [TICKETING Consumer] 處理預訂: booking_id={command.booking_id}')

            # 4. 調用 Gateway 處理業務邏輯
            result = await self.event_ticketing_gateway.handle_booking_created(command)

            # 5. 根據結果發送回應
            if result.is_success:
                await self.event_ticketing_gateway.send_success_response(result)
                Logger.base.info(
                    f'✅ [TICKETING Consumer] 處理成功: booking_id={command.booking_id}'
                )
            else:
                await self.event_ticketing_gateway.send_failure_response(
                    command.booking_id, result.error_message or 'Unknown error'
                )
                Logger.base.error(f'❌ [TICKETING Consumer] 處理失敗: {result.error_message}')

            return result.is_success

        except Exception as e:
            Logger.base.error(f'💥 [TICKETING Consumer] 處理異常: {e}')
            return False
