from datetime import datetime, timezone

from uuid_utils import UUID

from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToPendingPaymentAndTicketToReservedUseCase:
    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_broadcaster: IInMemoryEventBroadcaster,
    ):
        self.booking_command_repo = booking_command_repo
        self.event_broadcaster = event_broadcaster

    @Logger.io
    async def execute(
        self,
        *,
        booking_id: UUID,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        reserved_seats: list[str],
        seat_prices: dict[str, int],
        total_price: int,
    ) -> Booking:
        """
        Flow:
        1. Check if booking exists
        2. If exists: return existing booking (idempotency)
        3. If not exists: create booking + tickets atomically
        """
        # Validation - Fail Fast
        if not reserved_seats:
            raise ValueError('reserved_seats cannot be empty')

        # Convert seat identifiers from 'section-subsection-row-seat' to 'row-seat' format
        # Seat Reservation Service sends: ['A-1-1-3', 'A-1-1-4']
        # PostgreSQL expects: ['1-3', '1-4']
        seat_positions = []
        for seat_id in reserved_seats:
            parts = seat_id.split('-')
            if len(parts) == 4:  # section-subsection-row-seat
                row_seat = f'{parts[2]}-{parts[3]}'  # Extract row-seat only
                seat_positions.append(row_seat)
            else:
                Logger.base.warning(
                    f'⚠️ [UPSERT-BOOKING] Invalid seat format: {seat_id} (expected section-subsection-row-seat)'
                )

        if not seat_positions:
            raise ValueError('No valid seat positions after conversion')

        # Convert seat_prices keys from 'section-subsection-row-seat' to 'row-seat'
        converted_prices = {}
        for seat_id, price in seat_prices.items():
            parts = seat_id.split('-')
            if len(parts) == 4:
                row_seat = f'{parts[2]}-{parts[3]}'
                converted_prices[row_seat] = price

        # Use atomic upsert operation: create booking + tickets in 1 DB round-trip
        # This method is idempotent - if booking exists, returns existing
        # Returns dict with booking and tickets to avoid extra query
        result = await self.booking_command_repo.create_booking_with_tickets_directly(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=seat_positions,
            seat_prices=converted_prices,
            total_price=total_price,
        )

        upserted_booking = result['booking']
        tickets = result['tickets']

        Logger.base.info(
            f'✅ [UPSERT-BOOKING] Created/updated booking {booking_id} to PENDING_PAYMENT '
            f'with {len(tickets)} RESERVED tickets (total: {total_price})'
        )

        # Broadcast SSE event for real-time updates
        try:
            await self.event_broadcaster.broadcast(
                booking_id=booking_id,
                event_data={
                    'event_type': 'status_update',
                    'booking_id': str(booking_id),
                    'status': 'pending_payment',
                    'total_price': total_price,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'tickets': [
                        {
                            'id': ticket.id,
                            'section': ticket.section,
                            'subsection': ticket.subsection,
                            'row': ticket.row,
                            'seat_num': ticket.seat,
                            'price': ticket.price,
                            'status': ticket.status.value,
                            'seat_identifier': f'{ticket.section}-{ticket.subsection}-{ticket.row}-{ticket.seat}',
                        }
                        for ticket in tickets
                    ],
                },
            )
            Logger.base.debug(f'📡 [SSE] Broadcasted status update for booking {booking_id}')
        except Exception as e:
            # Don't fail use case if broadcast fails
            Logger.base.warning(f'⚠️ [SSE] Failed to broadcast event: {e}')

        return upserted_booking
