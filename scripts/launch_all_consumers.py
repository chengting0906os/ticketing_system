#!/usr/bin/env python
"""
Interactive Event Service Launcher
互動式活動服務啟動器 - 從資料庫獲取活動列表並啟動對應服務
"""

import asyncio
import sys
import os
from typing import List, Optional

from sqlalchemy import select

from src.shared.config.db_setting import get_async_session
from src.event_ticketing.infra.event_model import EventModel
from src.shared.event_bus.kafka_config_service import KafkaConfigService
from src.shared.event_bus.kafka_constant_builder import KafkaTopicBuilder, PartitionKeyBuilder
from src.shared.logging.loguru_io import Logger


class EventServiceLauncher:
    """
    智能活動服務啟動器

    功能：
    1. 從資料庫獲取所有活動
    2. 顯示互動式選單
    3. 啟動選中活動的所有服務
    """

    def __init__(self):
        self.kafka_service = KafkaConfigService()

    async def get_all_events(self) -> List[EventModel]:
        """從資料庫獲取所有活動"""
        async for session in get_async_session():
            try:
                result = await session.execute(
                    select(EventModel)
                    .where(EventModel.is_active == True)
                    .order_by(EventModel.id.desc())
                )
                events = result.scalars().all()
                return list(events)
            finally:
                await session.close()
        return []  # 確保所有路徑都有返回值

    async def display_event_menu(self, events: List[EventModel]) -> Optional[EventModel]:
        """顯示活動選單並獲取用戶選擇"""
        print("\n" + "=" * 60)
        print("🎫 活動服務啟動器 - Event Service Launcher")
        print("=" * 60)

        if not events:
            print("❌ 沒有找到任何活動")
            return None

        print(f"\n📋 找到 {len(events)} 個活動：\n")

        # 顯示活動列表
        for idx, event in enumerate(events, 1):
            # EventModel 可能沒有 created_at，改用 id 來排序
            seat_count = self._calculate_seat_count(event.seating_config)

            print(f"  {idx}. [{event.id}] {event.name}")
            print(f"     📍 {event.venue_name}")
            print(f"     💺 {seat_count:,} 個座位")
            print(f"     {'✅ 啟用中' if event.is_active else '⏸️ 已停用'}")
            print()

        print(f"  0. 退出")
        print("-" * 60)

        # 獲取用戶選擇
        while True:
            try:
                choice = input("\n請選擇要啟動服務的活動編號: ")
                choice_num = int(choice)

                if choice_num == 0:
                    print("👋 退出啟動器")
                    return None

                if 1 <= choice_num <= len(events):
                    selected_event = events[choice_num - 1]
                    return selected_event
                else:
                    print(f"❌ 請輸入 0 到 {len(events)} 之間的數字")

            except ValueError:
                print("❌ 請輸入有效的數字")
            except KeyboardInterrupt:
                print("\n👋 使用者中斷，退出啟動器")
                return None

    def _calculate_seat_count(self, seating_config: dict) -> int:
        """計算座位總數"""
        total = 0
        sections = seating_config.get('sections', [])

        for section in sections:
            for subsection in section.get('subsections', []):
                rows = subsection.get('rows', 0)
                seats_per_row = subsection.get('seats_per_row', 0)
                total += rows * seats_per_row

        return total

    async def launch_event_services(self, event: EventModel) -> None:
        """啟動特定活動的所有服務"""
        print("\n" + "=" * 60)
        print(f"🚀 正在為活動 [{event.id}] {event.name} 啟動服務...")
        print("=" * 60)

        # 1. 檢查並創建 Kafka topics
        print("\n📡 Step 1: 配置 Kafka Topics...")
        await self._ensure_kafka_topics(event)

        # 2. 啟動所有 consumers
        print("\n🎯 Step 2: 啟動 Event-Specific Consumers...")
        await self._start_consumers(event)

        # 3. 顯示啟動狀態
        print("\n" + "=" * 60)
        print("✅ 服務啟動完成！")
        print("=" * 60)
        self._display_service_info(event)

    async def _ensure_kafka_topics(self, event: EventModel) -> None:
        """確保 Kafka topics 存在"""
        topics = KafkaTopicBuilder.get_all_topics(event_id=event.id)

        for topic in topics:
            print(f"  📌 檢查 topic: {topic}")

        # 使用 KafkaConfigService 創建 topics
        await self.kafka_service._create_event_topics(event.id)

    async def _start_consumers(self, event: EventModel) -> None:
        """啟動所有 consumers (開發模式: 1:2:1 架構)"""
        consumers = [
            # 1:2:1 架構 - 開發模式也可以測試真實的負載分配
            ("📚 Booking Service Consumer", "src.booking.infra.booking_mq_consumer"),
            ("🪑 Seat Reservation Consumer #1", "src.seat_reservation.infra.seat_reservation_consumer"),
            ("🪑 Seat Reservation Consumer #2", "src.seat_reservation.infra.seat_reservation_consumer"),
            ("🎫 Event Ticketing Consumer", "src.event_ticketing.infra.event_ticketing_mq_consumer")
        ]

        # 獲取項目根目錄
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for desc, module in consumers:
            print(f"  {desc}")

            # 設置環境變數
            env = os.environ.copy()
            env["EVENT_ID"] = str(event.id)
            env["PYTHONPATH"] = project_root

            # 啟動 consumer
            cmd = ["uv", "run", "python", "-m", module]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=project_root,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True
                )

                print(f"    ✅ 啟動成功 (PID: {process.pid})")

            except Exception as e:
                print(f"    ❌ 啟動失敗: {e}")

    def _display_service_info(self, event: EventModel) -> None:
        """顯示服務資訊"""
        seat_count = self._calculate_seat_count(event.seating_config)

        print(f"""
📊 服務狀態摘要 (🛠️ 開發模式 - 1:2:1 架構)：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  活動 ID:     {event.id}
  活動名稱:    {event.name}
  場地:        {event.venue_name}
  座位數:      {seat_count:,}

  主要 Topics:""" + "\n".join([f"    • {topic}" for topic in KafkaTopicBuilder.get_all_topics(event_id=event.id)]) + """

  Consumer 配置 (1:2:1 架構):
    • 📚 Booking Service (1個) ✅
    • 🪑 Seat Reservation (2個) ✅
    • 🎫 Event Ticketing (1個) ✅

  🛠️ 開發模式: 使用真實的 1:2:1 架構來測試負載分配
  🚀 生產環境: 直接使用相同架構，只需調整 partition 數量
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 提示: 使用 Ctrl+C 停止所有服務
        """)

    async def run(self):
        """主程式入口"""
        try:
            # 1. 獲取所有活動
            print("🔍 正在從資料庫獲取活動列表...")
            events = await self.get_all_events()

            # 2. 顯示選單並獲取選擇
            selected_event = await self.display_event_menu(events)

            if selected_event:
                # 3. 啟動服務
                await self.launch_event_services(selected_event)

                # 4. 等待用戶中斷
                print("\n按 Ctrl+C 停止所有服務...")
                try:
                    await asyncio.Event().wait()
                except KeyboardInterrupt:
                    print("\n\n🛑 正在停止所有服務...")
                    # TODO: 實現服務停止邏輯
                    print("✅ 所有服務已停止")

        except Exception as e:
            Logger.base.error(f"❌ 啟動器發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


async def main():
    """主函數"""
    launcher = EventServiceLauncher()
    await launcher.run()


if __name__ == "__main__":
    # 使用 asyncio 運行主程式
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再見！")