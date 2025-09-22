"""
Event Ticketing Service 的事件處理器
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.event_ticketing.use_case.validate_tickets_use_case import ValidateTicketsUseCase
from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import EventHandler
from src.shared.event_bus.event_publisher import publish_domain_event
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_ticket_repo


class TicketingEventHandler(EventHandler):
    """處理 Event Ticketing Service 相關的事件"""

    def __init__(self):
        self.session = None
        self.ticket_repo = None
        self._initialized = False

    async def _ensure_initialized(self):
        """確保依賴項已初始化"""
        if not self._initialized:
            self.session = await get_async_session().__anext__()
            if self.session:
                self.ticket_repo = get_ticket_repo(self.session)
                self._initialized = True

    async def can_handle(self, event_type: str) -> bool:
        """檢查是否可以處理指定的事件類型"""
        return event_type == 'BookingCreated'

    async def handle(self, event_data: Dict[str, Any]) -> None:
        """處理事件"""
        await self._ensure_initialized()

        event_type = event_data.get('event_type')

        if event_type == 'BookingCreated':
            await self._handle_booking_created(event_data)

    async def _handle_booking_created(self, event_data: Dict[str, Any]):
        """處理 BookingCreated 事件"""
        try:
            # 從 BookingCreated 事件中提取預訂資料
            aggregate_id = event_data.get('aggregate_id')  # 這是 booking_id
            data = event_data.get('data', {})
            buyer_id = data.get('buyer_id')
            event_id = data.get('event_id')

            if not aggregate_id or not buyer_id or not event_id:
                Logger.base.error('Missing required fields in BookingCreated event')
                await self._send_booking_failed_event(
                    str(aggregate_id or 0), 'Missing required fields'
                )
                return

            # 獲取預訂以提取 ticket_ids
            try:
                from src.shared.service.repo_di import get_booking_query_repo

                booking_query_repo = get_booking_query_repo(self.session)  # type: ignore
                booking = await booking_query_repo.get_by_id(booking_id=aggregate_id)
                if not booking or not booking.ticket_ids:
                    Logger.base.error(f'Booking {aggregate_id} not found or has no ticket_ids')
                    await self._send_booking_failed_event(
                        str(aggregate_id), 'Booking not found or invalid'
                    )
                    return

                # 使用 ValidateTicketsUseCase 來預留指定的票務
                if self.session and self.ticket_repo:
                    validate_use_case = ValidateTicketsUseCase(
                        session=self.session, ticket_repo=self.ticket_repo
                    )
                    await validate_use_case.reserve_tickets(
                        ticket_ids=booking.ticket_ids, buyer_id=buyer_id
                    )

                # 向預訂服務發送成功事件
                await self._send_booking_success_event(
                    booking_id=aggregate_id, buyer_id=buyer_id, ticket_ids=booking.ticket_ids
                )

            except Exception as e:
                Logger.base.error(f'Failed to reserve tickets for booking {aggregate_id}: {e}')
                await self._send_booking_failed_event(str(aggregate_id), str(e))
            finally:
                if self.session:
                    await self.session.close()

        except Exception as e:
            Logger.base.error(f'Error handling BookingCreated event: {e}')

    async def _send_booking_success_event(
        self, booking_id: int, buyer_id: int, ticket_ids: List[int]
    ):
        """向預訂服務發送預訂成功事件"""

        @dataclass
        class TicketsReserved:
            booking_id: int
            buyer_id: int
            ticket_ids: List[int]
            status: str = 'reserved'
            occurred_at: datetime = None  # type: ignore

            def __post_init__(self):
                if self.occurred_at is None:
                    self.occurred_at = datetime.now(timezone.utc)

            @property
            def aggregate_id(self) -> int:
                return self.booking_id

        event = TicketsReserved(
            booking_id=booking_id,
            buyer_id=buyer_id,
            ticket_ids=ticket_ids,
        )

        # 使用 booking_id 作為分區鍵以確保正確的順序
        partition_key = str(booking_id)

        await publish_domain_event(
            event=event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_RESPONSE.value,
            partition_key=partition_key,
        )

        Logger.base.info(f'Sent TicketsReserved event for booking {booking_id}')

    async def _send_booking_failed_event(self, booking_id: str, error_message: str):
        """向預訂服務發送預訂失敗事件"""
        from dataclasses import dataclass
        from datetime import datetime, timezone

        @dataclass
        class TicketReservationFailed:
            booking_id: str
            error_message: str
            status: str = 'failed'
            occurred_at: datetime = None  # type: ignore

            def __post_init__(self):
                if self.occurred_at is None:
                    self.occurred_at = datetime.now(timezone.utc)

            @property
            def aggregate_id(self) -> str:
                return self.booking_id

        event = TicketReservationFailed(
            booking_id=booking_id,
            error_message=error_message,
        )

        await publish_domain_event(
            event=event,  # type: ignore
            topic=Topic.TICKETING_BOOKING_RESPONSE.value,
            partition_key=booking_id,
        )

        Logger.base.info(f'Sent TicketReservationFailed event for booking {booking_id}')
