from typing import List

from fastapi import Depends

from src.platform.database.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.domain.domain_event.booking_events import BookingCreated
from src.service.ticketing.domain.entity.booking_entity import Booking


class CreateBookingUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def create_booking(
        self,
        *,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        quantity: int,
    ) -> Booking:
        # Use domain entity's create method which contains all validation logic
        booking = Booking.create(
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            seat_positions=seat_positions,
            quantity=quantity,
        )

        async with self.uow:
            try:
                created_booking = await self.uow.booking_command_repo.create(booking=booking)
            except Exception as e:
                raise DomainError(f'{e}', 400)

            # UoW commits the transaction
            await self.uow.commit()

        # Publish domain event after successful commit
        booking_created_event = BookingCreated.from_booking(created_booking)
        Logger.base.info(
            f'\033[94m📤 [BOOKING UseCase] 發送事件到 Topic: {KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(event_id=booking.event_id)}\033[0m'
        )
        Logger.base.info(
            f'\033[93m📦 [BOOKING UseCase] 事件內容: event_id={created_booking.event_id}, buyer_id={created_booking.buyer_id}, seat_mode={created_booking.seat_selection_mode}\033[0m'
        )
        await publish_domain_event(
            event=booking_created_event,
            topic=KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
                event_id=booking.event_id
            ),
            partition_key=str(created_booking.id),
        )

        Logger.base.info(
            '\033[92m✅ [BOOKING UseCase] 事件發送完成！等待 event_ticketing 服務處理...\033[0m'
        )

        return created_booking
