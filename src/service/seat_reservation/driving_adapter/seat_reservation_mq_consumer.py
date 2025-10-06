"""
Seat Reservation Consumer - 座位選擇路由器
職責:管理 Kvrocks 座位狀態並處理預訂請求
"""

from dataclasses import dataclass
import json
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from anyio.from_thread import BlockingPortal, start_blocking_portal
from quixstreams import Application


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import settings
from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.service.seat_reservation.app.command.finalize_seat_payment_use_case import (
    FinalizeSeatPaymentRequest,
)
from src.service.seat_reservation.app.command.release_seat_use_case import ReleaseSeatRequest
from src.service.seat_reservation.app.command.reserve_seats_use_case import ReservationRequest


@dataclass
class KafkaConfig:
    """Kafka 配置"""

    commit_interval: float = 0.5
    retries: int = 3

    @property
    def producer_config(self) -> Dict:
        return {
            'enable.idempotence': True,
            'acks': 'all',
            'retries': self.retries,
        }

    @property
    def consumer_config(self) -> Dict:
        return {
            'enable.auto.commit': False,
            'auto.offset.reset': 'earliest',
        }


class SeatReservationConsumer:
    """
    座位預訂消費者 - 無狀態路由器

    監聽 3 個 Topics:
    1. ticket_reserving_request_to_reserved_in_kvrocks - 預訂請求
    2. release_ticket_status_to_available_in_kvrocks - 釋放座位
    3. finalize_ticket_status_to_paid_in_kvrocks - 完成支付
    """

    def __init__(self):
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )

        self.kafka_config = KafkaConfig()
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None

        # Use cases (延遲初始化)
        self.reserve_seats_use_case: Any = None
        self.release_seat_use_case: Any = None
        self.finalize_seat_payment_use_case: Any = None

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """設置 BlockingPortal 用於同步調用 async 函數"""
        self.portal = portal

    @Logger.io
    def _create_kafka_app(self) -> Application:
        """創建無狀態 Kafka 應用"""
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            commit_interval=self.kafka_config.commit_interval,
            producer_extra_config=self.kafka_config.producer_config,
            consumer_extra_config=self.kafka_config.consumer_config,
        )

        Logger.base.info(
            f'🪑 [SEAT-RESERVATION] Created stateless Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}'
        )
        return app

    @Logger.io
    def _setup_topics(self):
        """設置 3 個 topic 的處理邏輯"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # 定義 topic 配置
        topics = {
            'reservation': (
                KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
                    event_id=self.event_id
                ),
                self._process_reservation_request,
            ),
            'release': (
                KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                    event_id=self.event_id
                ),
                self._process_release_seat,
            ),
            'finalize': (
                KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(event_id=self.event_id),
                self._process_finalize_payment,
            ),
        }

        # 註冊所有 topics
        for name, (topic_name, handler) in topics.items():
            topic = self.kafka_app.topic(
                name=topic_name,
                key_serializer='str',
                value_serializer='json',
            )
            self.kafka_app.dataframe(topic=topic).apply(handler, stateful=False)
            Logger.base.info(f'   ✓ {name.capitalize()} topic configured')

        Logger.base.info('✅ All topics configured (stateless mode)')

    # ========== Message Handlers ==========

    @Logger.io
    def _process_reservation_request(self, message: Dict) -> Dict:
        """處理預訂請求"""
        try:
            Logger.base.info(f'🎫 [RESERVATION] Processing: {message.get("aggregate_id")}')
            result = self.portal.call(self._handle_reservation, message)
            return {'success': True, 'result': result}
        except Exception as e:
            Logger.base.error(f'❌ [RESERVATION] Failed: {e}')
            return {'success': False, 'error': str(e)}

    @Logger.io
    def _process_release_seat(self, message: Dict) -> Dict:
        """處理釋放座位"""
        seat_id = message.get('seat_id')
        if not seat_id:
            return {'success': False, 'error': 'Missing seat_id'}

        try:
            request = ReleaseSeatRequest(seat_id=seat_id, event_id=self.event_id)
            result = self.portal.call(self.release_seat_use_case.execute, request)

            if result.success:
                Logger.base.info(f'🔓 [RELEASE] {seat_id}')
                return {'success': True, 'seat_id': seat_id}

            return {'success': False, 'error': result.error_message}

        except Exception as e:
            Logger.base.error(f'❌ [RELEASE] {e}')
            return {'success': False, 'error': str(e)}

    @Logger.io
    def _process_finalize_payment(self, message: Dict) -> Dict:
        """處理完成支付"""
        seat_id = message.get('seat_id')
        if not seat_id:
            return {'success': False, 'error': 'Missing seat_id'}

        try:
            request = FinalizeSeatPaymentRequest(
                seat_id=seat_id,
                event_id=self.event_id,
                timestamp=message.get('timestamp', ''),
            )

            result = self.portal.call(self.finalize_seat_payment_use_case.execute, request)

            if result.success:
                Logger.base.info(f'💰 [FINALIZE] {seat_id}')
                return {'success': True, 'seat_id': seat_id}

            return {'success': False, 'error': result.error_message}

        except Exception as e:
            Logger.base.error(f'❌ [FINALIZE] {e}')
            return {'success': False, 'error': str(e)}

    # ========== Reservation Logic ==========

    @Logger.io
    async def _handle_reservation(self, event_data: Any) -> bool:
        """處理座位預訂事件 - 只負責路由到 use case"""
        try:
            parsed = self._parse_event_data(event_data)
            if not parsed:
                Logger.base.error('❌ [RESERVATION] Failed to parse event data')
                return False

            command = self._create_reservation_command(parsed)
            Logger.base.info(f'🎯 [RESERVATION] booking_id={command["booking_id"]}')

            await self._execute_reservation(command)
            return True

        except Exception as e:
            Logger.base.error(f'💥 [RESERVATION] Exception: {e}')
            return False

    @Logger.io
    def _parse_event_data(self, event_data: Any) -> Optional[Dict]:
        """解析事件數據"""
        try:
            if isinstance(event_data, dict):
                return event_data
            if isinstance(event_data, str):
                return json.loads(event_data)
            if hasattr(event_data, '__dict__'):
                return dict(vars(event_data))

            Logger.base.error(f'❌ Unknown event data type: {type(event_data)}')
            return None

        except Exception as e:
            Logger.base.error(f'❌ Parse failed: {e}')
            return None

    @Logger.io
    def _create_reservation_command(self, event_data: Dict) -> Dict:
        """創建預訂命令

        Note: publish_domain_event spreads event fields with **event.__dict__
        and removes 'aggregate_id' to avoid duplication. All fields including
        booking_id, buyer_id, event_id are at top level.
        """
        booking_id = event_data.get('booking_id')
        buyer_id = event_data.get('buyer_id')
        event_id = event_data.get('event_id')

        if not all([booking_id, buyer_id, event_id]):
            raise ValueError('Missing required fields in event data')

        return {
            'booking_id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'section': event_data.get('section', ''),
            'subsection': event_data.get('subsection', 0),
            'quantity': event_data.get('quantity', 2),
            'seat_selection_mode': event_data.get('seat_selection_mode', 'best_available'),
            'seat_positions': event_data.get('seat_positions', []),
        }

    @Logger.io
    async def _execute_reservation(self, command: Dict) -> bool:
        """執行座位預訂 - 只負責調用 use case"""
        try:
            Logger.base.info(
                f'🪑 [EXECUTE] booking={command["booking_id"]}, '
                f'section={command["section"]}-{command["subsection"]}, '
                f'qty={command["quantity"]}, mode={command["seat_selection_mode"]}'
            )

            request = ReservationRequest(
                booking_id=command['booking_id'],
                buyer_id=command['buyer_id'],
                event_id=command['event_id'],
                selection_mode=command['seat_selection_mode'],
                quantity=command['quantity'],
                seat_positions=command['seat_positions'],
                section_filter=command['section'],
                subsection_filter=command['subsection'],
            )

            # 調用 use case (use case 會負責發送成功/失敗事件)
            await self.reserve_seats_use_case.reserve_seats(request)
            return True

        except Exception as e:
            Logger.base.error(f'❌ [EXECUTE] Exception: {e}')
            return False

    # ========== Lifecycle ==========

    def start(self):
        """啟動服務"""
        try:
            # 初始化 use cases
            self.reserve_seats_use_case = container.reserve_seats_use_case()
            self.release_seat_use_case = container.release_seat_use_case()
            self.finalize_seat_payment_use_case = container.finalize_seat_payment_use_case()

            # 設置 Kafka
            self._setup_topics()

            Logger.base.info(
                f'🚀 [SEAT-RESERVATION-{self.instance_id}] Started\n'
                f'   📊 Event: {self.event_id}\n'
                f'   👥 Group: {self.consumer_group_id}'
            )

            self.running = True
            if self.kafka_app:
                self.kafka_app.run()

        except Exception as e:
            Logger.base.error(f'❌ Start failed: {e}')
            raise

    def stop(self):
        """停止服務"""
        if not self.running:
            return

        self.running = False

        if self.kafka_app:
            try:
                Logger.base.info('🛑 Stopping Kafka app...')
                self.kafka_app = None
            except Exception as e:
                Logger.base.warning(f'⚠️ Stop error: {e}')

        Logger.base.info('🛑 Consumer stopped')


def main():
    consumer = SeatReservationConsumer()
    try:
        # 啟動 BlockingPortal，創建共享的 event loop
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)
            consumer.start()

    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
        try:
            consumer.stop()
        except Exception:
            pass
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')
        try:
            consumer.stop()
        except:
            pass
    finally:
        Logger.base.info('🧹 Cleaning up resources...')


if __name__ == '__main__':
    main()
