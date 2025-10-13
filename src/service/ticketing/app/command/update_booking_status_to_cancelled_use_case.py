from datetime import datetime, timezone

from fastapi import Depends

from src.platform.database.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
)
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToCancelledUseCase:
    """
    Update booking status to CANCELLED

    Dependencies:
    - booking_command_repo: For reading and updating booking
    - event_ticketing_query_repo: For querying ticket details (seat positions)
    """

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_ticketing_query_repo: IEventTicketingQueryRepo,
    ):
        self.booking_command_repo = booking_command_repo
        self.event_ticketing_query_repo = event_ticketing_query_repo

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        """For FastAPI endpoint compatibility"""
        return cls(
            booking_command_repo=uow.booking_command_repo,
            event_ticketing_query_repo=uow.event_ticketing_query_repo,
        )

    @Logger.io
    async def execute(self, *, booking_id: int, buyer_id: int) -> Booking:
        """
        執行訂單狀態更新為取消

        Args:
            booking_id: 訂單 ID
            buyer_id: 買家 ID

        Returns:
            更新後的訂單

        Raises:
            NotFoundError: 訂單不存在
            ForbiddenError: 無權取消此訂單
            DomainError: 訂單狀態不允許取消（由 domain 層拋出）
        """
        # 查詢訂單（Fail Fast）
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # 驗證所有權（Fail Fast）
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        # 標記為取消狀態（domain 會驗證狀態轉換）
        cancelled_booking = booking.cancel()
        updated_booking = await self.booking_command_repo.update_status_to_cancelled(
            booking=cancelled_booking
        )

        # 查詢關聯的 ticket_ids
        ticket_ids = await self.booking_command_repo.get_ticket_ids_by_booking_id(
            booking_id=booking_id
        )

        # 取得座位位置資訊（用於釋放 Kvrocks 座位）
        seat_positions = []
        if ticket_ids:
            tickets = await self.event_ticketing_query_repo.get_tickets_by_ids(
                ticket_ids=ticket_ids
            )
            seat_positions = [
                ticket.seat_identifier for ticket in tickets if ticket.seat_identifier
            ]
            Logger.base.info(
                f'🎫 [CANCEL] Found {len(seat_positions)} seat positions: {seat_positions}'
            )

        # 發送 BookingCancelledEvent 到 Kafka（釋放 Kvrocks 座位）
        if ticket_ids:
            Logger.base.info(
                f'🔓 [CANCEL] Publishing cancellation event for {len(ticket_ids)} tickets'
            )

            cancelled_event = BookingCancelledEvent(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=booking.event_id,
                ticket_ids=ticket_ids,
                seat_positions=seat_positions,
                cancelled_at=datetime.now(timezone.utc),
            )

            topic_name = KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                event_id=booking.event_id
            )
            partition_key = f'event-{booking.event_id}'

            await publish_domain_event(
                event=cancelled_event, topic=topic_name, partition_key=partition_key
            )

            Logger.base.info(f'✅ [CANCEL] Published BookingCancelledEvent to {topic_name}')

        Logger.base.info(f'🎯 [CANCEL] Booking {booking_id} cancelled successfully')
        return updated_booking
