from pydantic import UUID7 as UUID
from src.platform.exception.exceptions import ForbiddenError, NotFoundError
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

    @Logger.io
    async def execute(
        self, *, booking_id: UUID, buyer_id: int, seat_identifiers: list[str]
    ) -> Booking:
        """
        Atomically reserve tickets and update booking to PENDING_PAYMENT (1 DB round-trip)

        Args:
            booking_id: Booking ID
            buyer_id: Buyer ID
            seat_identifiers: Seat identifiers (e.g., ['A-1-1-1', 'A-1-1-2'])

        Returns:
            Updated booking

        Raises:
            NotFoundError: Booking or tickets not found
            ForbiddenError: Booking ownership mismatch
            ValueError: Invalid seat identifiers or ticket availability
        """
        # Quick validation - Fail Fast
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError(f'Booking not found: booking_id={booking_id}')

        if booking.buyer_id != buyer_id:
            raise ForbiddenError(
                f'Booking owner mismatch: booking.buyer_id={booking.buyer_id}, buyer_id={buyer_id}'
            )

        if not seat_identifiers:
            raise ValueError('seat_identifiers cannot be empty')

        # Use atomic operation: reserve tickets + update booking in 1 DB round-trip
        # This replaces 5 separate queries with a single CTE
        (
            updated_booking,
            reserved_tickets,
            total_price,
        ) = await self.booking_command_repo.reserve_tickets_and_update_booking_atomically(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=booking.event_id,
            section=booking.section,
            subsection=booking.subsection,
            seat_identifiers=seat_identifiers,
        )

        Logger.base.info(
            f'✅ [BOOKING] Atomically reserved {len(reserved_tickets)} tickets '
            f'and updated booking {booking_id} to PENDING_PAYMENT (total: {total_price})'
        )

        return updated_booking
