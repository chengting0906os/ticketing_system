from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.platform.config.di import Container
from src.platform.database.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingCreatedDomainEvent
from src.service.ticketing.domain.entity.booking_entity import Booking


class CreateBookingUseCase:
    def __init__(
        self,
        *,
        uow: AbstractUnitOfWork,
        event_publisher: IBookingEventPublisher,
        seat_availability_handler: ISeatAvailabilityQueryHandler,
    ):
        self.uow = uow
        self.event_publisher = event_publisher
        self.seat_availability_handler = seat_availability_handler

    @classmethod
    @inject
    def depends(
        cls,
        uow: AbstractUnitOfWork = Depends(get_unit_of_work),
        event_publisher: IBookingEventPublisher = Depends(
            Provide[Container.booking_event_publisher]
        ),
        seat_availability_handler: ISeatAvailabilityQueryHandler = Depends(
            Provide[Container.seat_availability_query_handler]
        ),
    ):
        return cls(
            uow=uow,
            event_publisher=event_publisher,
            seat_availability_handler=seat_availability_handler,
        )

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
        # Fail Fast: Check seat availability before creating booking
        has_enough_seats = await self.seat_availability_handler.check_subsection_availability(
            event_id=event_id,
            section=section,
            subsection=subsection,
            required_quantity=quantity,
        )

        if not has_enough_seats:
            raise DomainError(
                f'Insufficient seats available in section {section}-{subsection}', 400
            )

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

        # Publish domain event after successful commit (using abstraction)
        booking_created_event = BookingCreatedDomainEvent.from_booking(created_booking)
        await self.event_publisher.publish_booking_created(event=booking_created_event)

        return created_booking
