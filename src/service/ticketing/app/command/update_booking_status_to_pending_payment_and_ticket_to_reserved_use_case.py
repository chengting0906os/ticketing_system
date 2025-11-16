from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace
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
        self.tracer = trace.get_tracer(__name__)

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
        total_price: int,
        subsection_stats: dict | None = None,
        event_stats: dict | None = None,
    ) -> Booking:
        """
        Flow:
        1. Check if booking exists
        2. If exists: return existing booking (idempotency)
        3. If not exists: create booking + tickets atomically
        """
        with self.tracer.start_as_current_span(
            'use_case.update_booking_to_pending_payment',
            attributes={
                'booking.id': str(booking_id),
                'event.id': event_id,
                'buyer.id': buyer_id,
                'seat.section': section,
                'seat.subsection': subsection,
                'seat.mode': seat_selection_mode,
                'seats.count': len(reserved_seats),
                'booking.total_price': total_price,
            },
        ):
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
                # Convert TicketRef objects to dicts for JSON serialization
                ticket_dicts = []
                for ticket in tickets:
                    ticket_dict = {
                        'id': ticket.id,
                        'section': ticket.section,
                        'subsection': ticket.subsection,
                        'row': ticket.row,
                        'seat_num': ticket.seat,
                        'price': ticket.price,
                        'status': ticket.status.value,
                        'seat_identifier': f'{ticket.section}-{ticket.subsection}-{ticket.row}-{ticket.seat}',
                    }
                    ticket_dicts.append(ticket_dict)

                event_data: dict[str, Any] = {
                    'event_type': 'status_update',
                    'booking_id': str(booking_id),
                    'status': 'pending_payment',
                    'total_price': total_price,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'tickets': ticket_dicts,
                }

                # Only include stats if they have values (not None and not empty)
                if subsection_stats:
                    event_data['subsection_stats'] = subsection_stats
                if event_stats:
                    event_data['event_stats'] = event_stats

                await self.event_broadcaster.broadcast(
                    booking_id=booking_id,
                    event_data=event_data,
                )
            except Exception as e:
                # Don't fail use case if broadcast fails
                Logger.base.warning(f'⚠️ [SSE] Failed to broadcast event: {e}')

            return upserted_booking
