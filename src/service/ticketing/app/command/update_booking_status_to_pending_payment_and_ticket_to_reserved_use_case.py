from fastapi import Depends

from src.platform.database.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import TicketStatus
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToPendingPaymentAndTicketToReservedUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def execute(
        self, *, booking_id: int, buyer_id: int, seat_identifiers: list[str]
    ) -> Booking:
        """
        執行訂單狀態更新為待付款，並將票券狀態更新為已預訂

        Args:
            booking_id: 訂單 ID
            buyer_id: 買家 ID
            seat_identifiers: 座位標識符列表 (例如: ['A-1-1-1', 'A-1-1-2'])

        Returns:
            更新後的訂單

        Raises:
            NotFoundError: 找不到訂單或票券
            ForbiddenError: 訂單所有者不符
        """
        Logger.base.critical('🚩 [UoW] Start UpdateBookingToPendingPaymentAndTicketTo)')
        async with self.uow:
            # 查詢訂單 - Fail Fast
            booking = await self.uow.booking_command_repo.get_by_id(booking_id=booking_id)
            if not booking:
                raise NotFoundError(f'Booking not found: booking_id={booking_id}')

            # 驗證所有權 - Fail Fast
            if booking.buyer_id != buyer_id:
                raise ForbiddenError(
                    f'Booking owner mismatch: booking.buyer_id={booking.buyer_id}, buyer_id={buyer_id}'
                )

            # 0. 將座位標識符轉換為票券 ID (Fail Fast)
            ticket_ids = []
            if seat_identifiers:
                ticket_ids = (
                    await self.uow.event_ticketing_command_repo.get_ticket_ids_by_seat_identifiers(
                        event_id=booking.event_id, seat_identifiers=seat_identifiers
                    )
                )

                if len(ticket_ids) != len(seat_identifiers):
                    raise NotFoundError(
                        f'Found {len(ticket_ids)} tickets for {len(seat_identifiers)} seat identifiers'
                    )

            # 1. 更新 tickets 狀態為 RESERVED (最核心操作，優先執行)
            if ticket_ids:
                await self.uow.event_ticketing_command_repo.update_tickets_status(
                    ticket_ids=ticket_ids, status=TicketStatus.RESERVED, buyer_id=buyer_id
                )
                Logger.base.info(f'🎫 [BOOKING] Reserved {len(ticket_ids)} tickets')

            # 2. 計算總價 (RESERVED 後查詢價格)
            total_price = 0
            if ticket_ids:
                tickets = await self.uow.event_ticketing_query_repo.get_tickets_by_ids(
                    ticket_ids=ticket_ids
                )
                total_price = sum(ticket.price for ticket in tickets)

                Logger.base.info(
                    f'💰 [BOOKING] Calculated total price: {total_price} '
                    f'for {len(ticket_ids)} tickets'
                )

            # 3. 更新 booking 狀態為 pending_payment 並設置總價和座位
            # 對於 best_available 模式，seat_identifiers 包含實際預訂到的座位
            pending_booking = booking.mark_as_pending_payment_and_update_newest_info(
                total_price=total_price,
                seat_positions=seat_identifiers,
            )

            updated_booking = await self.uow.booking_command_repo.update_status_to_pending_payment(
                booking=pending_booking
            )

            # 4. 寫入 booking_ticket 關聯表
            if ticket_ids:
                await self.uow.booking_command_repo.link_tickets_to_booking(
                    booking_id=booking_id, ticket_ids=ticket_ids
                )

            # UoW commits!
            await self.uow.commit()
            return updated_booking
