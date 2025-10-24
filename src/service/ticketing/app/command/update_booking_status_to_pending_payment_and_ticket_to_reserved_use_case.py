from opentelemetry import trace

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToPendingPaymentAndTicketToReservedUseCase:
    """
    Update booking to PENDING_PAYMENT and tickets to RESERVED using atomic operation

    Dependencies:
    - booking_command_repo: For atomic reservation operation
    """

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
    ):
        self.booking_command_repo = booking_command_repo
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def execute(
        self,
        *,
        booking_id: int,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_identifiers: list[str],
        ticket_price: int,
    ) -> Booking:
        """
        Atomically reserve tickets and update booking to PENDING_PAYMENT (1 DB round-trip)

        Args:
            booking_id: Booking ID
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            seat_identifiers: Seat identifiers (e.g., ['1-1', '1-2'])
            ticket_price: Price per ticket from Kvrocks (all seats same price per subsection)

        Returns:
            Updated booking

        Raises:
            NotFoundError: Booking or tickets not found
            ForbiddenError: Booking ownership mismatch
            ValueError: Invalid seat identifiers or ticket availability
        """
        with self.tracer.start_as_current_span(
            'use_case.update_booking_to_pending_payment',
            attributes={
                'booking_id': booking_id,
                'buyer_id': buyer_id,
                'event_id': event_id,
                'section': section,
                'subsection': subsection,
                'seat_count': len(seat_identifiers),
                'ticket_price': ticket_price,
            },
        ):
            # Use atomic operation: reserve tickets + update booking in 1 DB round-trip
            # This replaces 5 separate queries with a single CTE
            with self.tracer.start_as_current_span('db.reserve_tickets_atomically'):
                (
                    updated_booking,
                    reserved_tickets,
                    total_price,
                ) = await self.booking_command_repo.reserve_tickets_and_update_booking_atomically(
                    booking_id=booking_id,
                    buyer_id=buyer_id,
                    event_id=event_id,
                    section=section,
                    subsection=subsection,
                    seat_identifiers=seat_identifiers,
                    ticket_price=ticket_price,
                )

            Logger.base.info(
                f'✅ [BOOKING] Atomically reserved {len(reserved_tickets)} tickets '
                f'and updated booking {booking_id} to PENDING_PAYMENT (total: {total_price})'
            )

            return updated_booking
