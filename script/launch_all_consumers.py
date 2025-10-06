#!/usr/bin/env python
"""
Interactive Event Service Launcher
互動式活動服務啟動器 - 從資料庫獲取活動列表並啟動對應服務
"""

import asyncio
import os
import signal
import sys
from typing import Dict, List, Optional

from sqlalchemy import select

from src.platform.database.db_setting import get_async_session
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_config_service import KafkaConfigService
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.driven_adapter.model.event_model import EventModel


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
        self.consumer_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.log_tasks: List[asyncio.Task] = []

    async def get_all_events(self) -> List[EventModel]:
        """從資料庫獲取所有活動"""
        async for session in get_async_session():
            try:
                result = await session.execute(
                    select(EventModel).where(EventModel.is_active).order_by(EventModel.id.desc())
                )
                events = result.scalars().all()
                return list(events)
            finally:
                await session.close()
        return []  # 確保所有路徑都有返回值

    async def display_event_menu(self, events: List[EventModel]) -> Optional[EventModel]:
        """顯示活動選單並獲取用戶選擇"""
        print('\n' + '=' * 60)
        print('🎫 活動服務啟動器 - Event Service Launcher')
        print('=' * 60)

        if not events:
            print('❌ 沒有找到任何活動')
            return None

        print(f'\n📋 找到 {len(events)} 個活動：\n')

        # 顯示活動列表
        for idx, event in enumerate(events, 1):
            # EventModel 可能沒有 created_at，改用 id 來排序
            seat_count = self._calculate_seat_count(event.seating_config)

            print(f'  {idx}. [{event.id}] {event.name}')
            print(f'     📍 {event.venue_name}')
            print(f'     💺 {seat_count:,} 個座位')
            print(f'     {"✅ 啟用中" if event.is_active else "⏸️ 已停用"}')
            print()

        print('  0. 退出')
        print('-' * 60)

        # 獲取用戶選擇
        while True:
            try:
                choice = input('\n請選擇要啟動服務的活動編號: ')
                choice_num = int(choice)

                if choice_num == 0:
                    print('👋 退出啟動器')
                    return None

                if 1 <= choice_num <= len(events):
                    selected_event = events[choice_num - 1]
                    return selected_event
                else:
                    print(f'❌ 請輸入 0 到 {len(events)} 之間的數字')

            except ValueError:
                print('❌ 請輸入有效的數字')
            except KeyboardInterrupt:
                print('\n👋 使用者中斷，退出啟動器')
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

    async def _kill_existing_consumers(self) -> None:
        """停止所有現有的 consumer 進程"""
        import subprocess

        # 定義要殺死的進程名稱模式
        consumer_patterns = [
            'ticketing_mq_consumer',
            'seat_reservation_mq_consumer',
        ]

        for pattern in consumer_patterns:
            try:
                # 使用 pkill 殺死進程
                result = subprocess.run(['pkill', '-f', pattern], capture_output=True, text=True)

                if result.returncode == 0:
                    print(f'  ✅ 停止了 {pattern} 進程')
                else:
                    print(f'  ℹ️ 沒有找到運行中的 {pattern}')
            except Exception as e:
                print(f'  ⚠️ 停止 {pattern} 時出錯: {e}')

        # 等待一下確保進程完全停止
        await asyncio.sleep(1)
        print('  ✅ 所有舊的 consumers 已停止')

    async def _stream_consumer_logs(
        self, consumer_id: str, _desc: str, process: asyncio.subprocess.Process
    ) -> None:
        if not process.stdout:
            return

        try:
            async for line in process.stdout:
                try:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line:  # 只顯示非空行
                        print(f'[{consumer_id}] {decoded_line}')
                except UnicodeDecodeError:
                    # 如果無法解碼，使用 latin-1 作為備用
                    decoded_line = line.decode('latin-1').strip()
                    if decoded_line:
                        print(f'[{consumer_id}] {decoded_line}')
        except Exception as e:
            print(f'[{consumer_id}] 日誌串流錯誤: {e}')

    async def _stop_all_consumers(self) -> None:
        """停止所有 consumer processes"""
        print('\n🛑 正在終止 consumer processes...')

        # 取消所有 log 任務
        for task in self.log_tasks:
            if not task.done():
                task.cancel()

        # 等待任務取消
        if self.log_tasks:
            try:
                await asyncio.gather(*self.log_tasks, return_exceptions=True)
            except Exception:
                pass

        # 終止所有 processes
        for consumer_id, process in self.consumer_processes.items():
            try:
                if process.returncode is None:  # 還在運行
                    print(f'  停止 {consumer_id} (PID: {process.pid})')
                    process.terminate()
            except Exception as e:
                print(f'  終止 {consumer_id} 時出錯: {e}')

        # 等待 processes 結束
        if self.consumer_processes:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*[p.wait() for p in self.consumer_processes.values()]),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                print('  部分 processes 未在時限內結束，強制殺死...')
                # 強制殺死還在運行的 processes
                for consumer_id, process in self.consumer_processes.items():
                    try:
                        if process.returncode is None:
                            process.kill()
                            print(f'    強制殺死 {consumer_id}')
                    except Exception as e:
                        print(f'    殺死 {consumer_id} 時出錯: {e}')

    async def launch_event_services(self, event: EventModel) -> None:
        """啟動特定活動的所有服務"""
        print('\n' + '=' * 60)
        print(f'🚀 正在為活動 [{event.id}] {event.name} 啟動服務...')
        print('=' * 60)

        # 1. 先停止現有的 consumers
        print('\n🛑 Step 1: 停止現有的 Consumers...')
        await self._kill_existing_consumers()

        # 2. 檢查並創建 Kafka topics
        print('\n📡 Step 2: 配置 Kafka Topics...')
        await self._ensure_kafka_topics(event)

        # 3. 啟動所有 consumers
        print('\n🎯 Step 3: 啟動 Event-Specific Consumers...')
        await self._start_consumers(event)

        # 4. 顯示啟動狀態
        print('\n' + '=' * 60)
        print('✅ 服務啟動完成！')
        print('=' * 60)
        self._display_service_info(event)

    async def _ensure_kafka_topics(self, event: EventModel) -> None:
        """確保 Kafka topics 存在"""
        topics = KafkaTopicBuilder.get_all_topics(event_id=event.id)

        for topic in topics:
            print(f'  📌 檢查 topic: {topic}')

        # 使用 KafkaConfigService 創建 topics
        await self.kafka_service._create_event_topics(event.id)

    async def _start_consumers(self, event: EventModel) -> None:
        """啟動所有 consumers 並創建 log 串流任務"""
        consumers = [
            # 整合架構 - PostgreSQL 狀態管理 + Kvrocks 狀態管理
            (
                '🎫 Ticketing Service Consumer (PostgreSQL)',
                'src.service.ticketing.driving_adapter.mq_consumer.ticketing_mq_consumer',
                'ticketing-service',
            ),
            (
                '🪑 Seat Reservation Consumer (Kvrocks)',
                'src.service.seat_reservation.driving_adapter.seat_reservation_mq_consumer',
                'seat-reservation-service',
            ),
        ]

        # 獲取項目根目錄
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for desc, module, consumer_id in consumers:
            print(f'  {desc}')

            # 設置環境變數
            env = os.environ.copy()
            env['EVENT_ID'] = str(event.id)
            env['PYTHONPATH'] = project_root
            env['CONSUMER_INSTANCE_ID'] = '1'

            # 啟動 consumer
            cmd = ['uv', 'run', 'python', '-m', module]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=project_root,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,  # 將 stderr 重定向到 stdout
                    start_new_session=True,
                )

                # 儲存 process 參考
                self.consumer_processes[consumer_id] = process

                # 創建 log 串流任務
                log_task = asyncio.create_task(
                    self._stream_consumer_logs(consumer_id, desc, process)
                )
                self.log_tasks.append(log_task)

                print(f'    ✅ 啟動成功 (PID: {process.pid})')

            except Exception as e:
                print(f'    ❌ 啟動失敗: {e}')

    def _display_service_info(self, event: EventModel) -> None:
        """顯示服務資訊"""
        seat_count = self._calculate_seat_count(event.seating_config)

        print(
            f"""
📊 服務狀態摘要 (🛠️ 開發模式 - 整合架構)：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  活動 ID:     {event.id}
  活動名稱:    {event.name}
  場地:        {event.venue_name}
  座位數:      {seat_count:,}

  主要 Topics:"""
            + '\n'.join(
                [f'    • {topic}' for topic in KafkaTopicBuilder.get_all_topics(event_id=event.id)]
            )
            + """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 正在串流所有 consumer 日誌...

💡 提示: 使用 Ctrl+C 停止所有服務
        """
        )

    async def run(self):
        """主程式入口"""
        try:
            # 1. 獲取所有活動
            print('🔍 正在從資料庫獲取活動列表...')
            events = await self.get_all_events()

            # 2. 顯示選單並獲取選擇
            selected_event = await self.display_event_menu(events)

            if selected_event:
                # 3. 啟動服務
                await self.launch_event_services(selected_event)

                # 4. 等待用戶中斷
                print('\n按 Ctrl+C 停止所有服務...')
                try:
                    # 等待中斷信號
                    stop_event = asyncio.Event()

                    def signal_handler(*args):
                        stop_event.set()

                    # 設置信號處理器
                    loop = asyncio.get_event_loop()
                    loop.add_signal_handler(signal.SIGINT, signal_handler)
                    loop.add_signal_handler(signal.SIGTERM, signal_handler)

                    await stop_event.wait()
                except KeyboardInterrupt:
                    pass

                print('\n\n🛑 正在停止所有服務...')
                await self._stop_all_consumers()
                print('✅ 所有服務已停止')

        except Exception as e:
            Logger.base.error(f'❌ 啟動器發生錯誤: {e}')
            import traceback

            traceback.print_exc()
            await self._stop_all_consumers()
            sys.exit(1)


async def main():
    """主函數"""
    launcher = EventServiceLauncher()
    await launcher.run()


if __name__ == '__main__':
    # 使用 asyncio 運行主程式
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n👋 再見！')
