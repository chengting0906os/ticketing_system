#!/usr/bin/env python
"""
Kafka Topic Monitor
監控 Kafka Topics 的消息流動
實時顯示經過 topics 的所有消息
"""

import asyncio
import json
import orjson
from datetime import datetime
from typing import Dict, List, Any
from confluent_kafka.admin import AdminClient
from confluent_kafka import Consumer, KafkaError
import signal

from src.shared.message_queue.kafka_config_service import KafkaConfigService
from src.shared.message_queue.kafka_constant_builder import KafkaTopicBuilder
import src.shared.message_queue.proto.domain_event_pb2 as domain_event_pb2


class KafkaTopicMonitor:
    """
    通過 Kafka Admin API 和 Consumer API 監控所有 Consumer 的狀態
    """

    def __init__(self, event_id: int):
        self.event_id = event_id
        self.kafka_service = KafkaConfigService()
        self.admin_client = AdminClient({'bootstrap.servers': 'localhost:9092'})
        self.monitoring = True
        self.monitor_consumers: Dict[str, Consumer] = {}

    def get_consumer_groups(self) -> List[str]:
        """獲取所有 consumer groups"""
        # 定義預期的 consumer groups
        expected_groups = [
            f"booking-service-{self.event_id}",
            f"seat-reservation-service-{self.event_id}",
            f"event-ticketing-service-{self.event_id}"
        ]
        return expected_groups

    def get_consumer_group_details(self, group_id: str) -> Dict[str, Any]:
        """獲取 consumer group 的詳細信息"""
        try:
            # 獲取 consumer group 的 metadata
            # metadata = self.admin_client.list_consumer_groups([group_id])
            return {
                'group_id': group_id,
                'state': 'ACTIVE',  # 需要更複雜的邏輯來獲取實際狀態
                'members': []  # 需要更複雜的邏輯來獲取成員信息
            }
        except Exception as e:
            return {
                'group_id': group_id,
                'state': 'UNKNOWN',
                'error': str(e)
            }

    def create_monitor_consumer(self, topic: str, group_suffix: str) -> Consumer:
        """創建一個監控用的 consumer 來查看消息流"""
        config = {
            'bootstrap.servers': 'localhost:9092',
            'group.id': f'topic-monitor-{group_suffix}-{self.event_id}',
            'auto.offset.reset': 'earliest',  # 從最早的消息開始讀取
            'enable.auto.commit': True,  # 啟用自動提交
            'auto.commit.interval.ms': 1000,
            'max.poll.interval.ms': 300000,
            'session.timeout.ms': 30000,
            'heartbeat.interval.ms': 10000,
        }

        consumer = Consumer(config)
        consumer.subscribe([topic])
        return consumer

    def setup_monitor_consumers(self) -> None:
        """設置所有監控 consumers - 監聽所有 topics"""
        # 使用 get_all_topics 獲取所有 topics
        all_topics = KafkaTopicBuilder.get_all_topics(event_id=self.event_id)

        # 為每個 topic 分配一個簡短的名稱
        topic_names = {
            'ticket-reserve-request': 'BOOK-REQ',
            'update-ticket-status-to-reserved': 'TKT-RSRV',
            'update-booking-status-to-pending-payment': 'BOOK-PEND',
            'update-booking-status-to-failed': 'BOOK-FAIL',
            'update-ticket-status-to-paid': 'TKT-PAID',
            'update-ticket-status-to-available': 'TKT-AVAIL',
            'release-ticket-to-available-by-rocksdb': 'RDB-RELS',
            'finalize-ticket-to-paid-by-rocksdb': 'RDB-PAID',
            'seat-initialization-command': 'SEAT-INIT',
        }

        print(f"\n📡 準備監聽 {len(all_topics)} 個 topics...\n")

        for topic in all_topics:
            # 從 topic 名稱中提取 action 部分
            for key, short_name in topic_names.items():
                if key in topic:
                    name = short_name
                    break
            else:
                name = 'UNKNOWN'

            try:
                consumer = self.create_monitor_consumer(topic, name)
                self.monitor_consumers[name] = consumer
                print(f"✅ [{name}] 監聽: {topic.split('______')[1] if '______' in topic else topic}")
            except Exception as e:
                print(f"❌ [{name}] 無法創建監控: {e}")

        print(f"\n📊 開始監控 {len(self.monitor_consumers)} 個 topics...")
        print(f"🔍 監聽方式: 從最早的消息開始 (earliest)\n")

    async def monitor_messages(self) -> None:
        """監控消息流"""
        print("\n📊 開始監控消息流...\n")

        while self.monitoring:
            for name, consumer in self.monitor_consumers.items():
                try:
                    # Poll for messages (non-blocking)
                    msg = consumer.poll(timeout=1.0)  # 增加 timeout

                    if msg is None:
                        continue

                    if msg.error():
                        if msg.error().code() != KafkaError._PARTITION_EOF:
                            print(f"[{name.upper()}] ❌ Error: {msg.error()}")
                        continue

                    # Parse and display message
                    try:
                        timestamp = datetime.fromtimestamp(msg.timestamp()[1] / 1000).strftime('%H:%M:%S')

                        # 嘗試解析為 Protobuf
                        try:
                            # 解析 Protobuf 消息
                            proto_event = domain_event_pb2.MqDomainEvent()
                            proto_event.ParseFromString(msg.value())

                            # 提取事件信息
                            event_type = proto_event.event_type
                            event_id = proto_event.event_id

                            # 解析 data 欄位 (JSON)
                            if proto_event.data:
                                data = orjson.loads(proto_event.data)
                            else:
                                data = {}

                        except Exception as e:
                            # 如果 Protobuf 解析失敗，嘗試 JSON
                            try:
                                raw_value = msg.value().decode('utf-8')
                                value = json.loads(raw_value)
                                event_type = value.get('event_type', 'UNKNOWN')
                                data = value.get('data', {})
                            except:
                                print(f"[{timestamp}] [{name}] 無法解析的消息: {msg.value()[:50]}...")
                                continue

                        # 從 data 中提取信息
                        booking_id = data.get('booking_id')
                        buyer_id = data.get('buyer_id')
                        ticket_ids = data.get('ticket_ids', [])
                        event_id_from_data = data.get('event_id')

                        # 根據名稱選擇 emoji
                        if 'BOOK' in name:
                            emoji = '📚'
                        elif 'TKT' in name:
                            emoji = '🎫'
                        elif 'RDB' in name:
                            emoji = '💾'
                        elif 'SEAT' in name:
                            emoji = '🪑'
                        else:
                            emoji = '🔄'

                        # 構建顯示信息
                        info_parts = []
                        if event_id_from_data:
                            info_parts.append(f"event:{event_id_from_data}")
                        if booking_id:
                            info_parts.append(f"booking:{booking_id}")
                        if buyer_id:
                            info_parts.append(f"buyer:{buyer_id}")
                        if ticket_ids:
                            info_parts.append(f"tickets:{len(ticket_ids)}")

                        info = f" ({', '.join(info_parts)})" if info_parts else ""
                        print(f"[{timestamp}] {emoji} [{name}] {event_type}{info}")

                        # 顯示詳細信息（可選）
                        # print(f"    Details: {json.dumps(value, indent=2)}")

                    except Exception as e:
                        # 解析失敗
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        print(f"[{timestamp}] [{name}] Parse error: {str(e)[:100]}")

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"[{name}] Monitor error: {str(e)}[:100]")

            await asyncio.sleep(0.1)  # 稍微增加延遲

    async def show_consumer_lag(self) -> None:
        """顯示 consumer lag 信息"""
        while self.monitoring:
            print("\n" + "=" * 60)
            print(f"📊 Consumer Lag Report - {datetime.now().strftime('%H:%M:%S')}")
            print("=" * 60)

            for group_id in self.get_consumer_groups():
                details = self.get_consumer_group_details(group_id)
                state = details.get('state', 'UNKNOWN')

                # 顏色編碼狀態
                if state == 'ACTIVE':
                    state_display = "✅ ACTIVE"
                elif state == 'UNKNOWN':
                    state_display = "❓ UNKNOWN"
                else:
                    state_display = f"⚠️ {state}"

                print(f"\n{group_id}:")
                print(f"  Status: {state_display}")

                # TODO: 實現實際的 lag 計算
                # 這需要更複雜的邏輯來獲取 partition assignment 和 offset 信息

            await asyncio.sleep(30)  # Update every 30 seconds

    async def run(self):
        """主運行邏輯"""
        print("\n" + "=" * 60)
        print(f"🔍 Kafka Consumer Monitor - Event ID: {self.event_id}")
        print("=" * 60)

        # 設置監控 consumers
        self.setup_monitor_consumers()

        # 設置信號處理
        def signal_handler(_sig=None, _frame=None):
            print("\n\n🛑 Stopping monitor...")
            self.monitoring = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 創建並行任務
        tasks = [
            asyncio.create_task(self.monitor_messages()),
            # asyncio.create_task(self.show_consumer_lag()),  # 可選：顯示 lag 信息
        ]

        # 等待所有任務
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            pass
        finally:
            # 清理
            for consumer in self.monitor_consumers.values():
                consumer.close()
            print("✅ Monitor stopped")


async def main():
    """主函數"""
    import sys

    # 從命令行參數獲取 event_id
    if len(sys.argv) < 2:
        print("Usage: python kafka_consumer_monitor.py <event_id>")
        print("Example: python kafka_consumer_monitor.py 1")
        sys.exit(1)

    try:
        event_id = int(sys.argv[1])
    except ValueError:
        print("❌ Event ID must be a number")
        sys.exit(1)

    monitor = KafkaTopicMonitor(event_id)
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())