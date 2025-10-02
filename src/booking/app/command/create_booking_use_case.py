from typing import TYPE_CHECKING, List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import Booking
from src.booking.domain.booking_events import BookingCreated
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder


if TYPE_CHECKING:
    from src.booking.driven_adapter.booking_command_repo_impl import BookingCommandRepoImpl


class CreateBookingUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
    ):
        self.session = session
        self.booking_command_repo: 'BookingCommandRepoImpl' = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
    ):
        return cls(session=session, booking_command_repo=booking_command_repo)

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

        try:
            created_booking = await self.booking_command_repo.create(booking=booking)
        except Exception as e:
            raise DomainError(f'{e}', 400)

        # Commit the database transaction
        await self.session.commit()
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
