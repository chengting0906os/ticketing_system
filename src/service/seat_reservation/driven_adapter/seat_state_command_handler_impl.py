"""
Seat State Command Handler Implementation

CQRS Command Side implementation for seat state management.
"""

from typing import Dict, List, Optional

from opentelemetry import trace
import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.booking_status_manager import (
    BookingStatusManager,
)
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.seat_finder import (
    SeatFinder,
)
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


# Status constants
SEAT_STATUS_AVAILABLE = 0  # 00
SEAT_STATUS_RESERVED = 1  # 01
SEAT_STATUS_SOLD = 2  # 10

STATUS_TO_BITFIELD = {
    'available': SEAT_STATUS_AVAILABLE,
    'reserved': SEAT_STATUS_RESERVED,
    'sold': SEAT_STATUS_SOLD,
}


class SeatStateCommandHandlerImpl(ISeatStateCommandHandler):
    """
    Seat State Command Handler Implementation (CQRS Command)

    Responsibility: Orchestrates seat reservation workflow using specialized components:
    - BookingStatusManager: Handles idempotency and status management
    - SeatFinder: Finds consecutive available seats
    - LuaReservationExecutor: Executes atomic seat reservation
    """

    def __init__(self, booking_metadata_handler: IBookingMetadataHandler):
        """
        Initialize Seat State Command Handler.

        Args:
            booking_metadata_handler: Required. Injected via DI container.
        """
        self.booking_metadata_handler = booking_metadata_handler
        self.status_manager = BookingStatusManager(
            booking_metadata_handler=booking_metadata_handler
        )
        self.seat_finder = SeatFinder()
        self.reservation_executor = AtomicReservationExecutor()
        self._config_cache: Dict[
            tuple[int, str], Dict
        ] = {}  # Section config cache: (event_id, section_id) -> config dict
        self.tracer = trace.get_tracer(__name__)  # Initialize tracer for distributed tracing

    # ========== Helper Methods ==========

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    @staticmethod
    def _error_result(message: str) -> Dict:
        """Create standardized error result"""
        return {
            'success': False,
            'reserved_seats': [],
            'total_price': 0,
            'subsection_stats': {},
            'event_stats': {},
            'error_message': message,
        }

    # ========== Config & Validation ==========

    async def _get_section_config(self, event_id: int, section_id: str) -> Dict:
        cache_key = (event_id, section_id)
        if cache_key in self._config_cache:
            return self._config_cache[cache_key]

        # Cache miss - fetch from event config JSON
        try:
            client = kvrocks_client.get_client()
            event_state_key = make_event_state_key(event_id=event_id)
            result = await client.execute_command('JSON.GET', event_state_key, '$')

            if not result:
                raise ValueError(f'No event config found for event_id={event_id}')

            # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
            # Parse JSON string array and extract first element
            event_state_list = orjson.loads(result)
            event_state = event_state_list[0]
            section_name = section_id.split('-')[0]
            subsection_num = section_id.split('-')[1]
            section_config = event_state.get('sections', {}).get(section_name, {})
            subsection_config = section_config.get('subsections', {}).get(subsection_num, {})
            result = {
                'rows': int(subsection_config['rows']),
                'seats_per_row': int(subsection_config['seats_per_row']),
                'price': int(section_config['price']),  # Price from section level
            }

            # Store in cache
            self._config_cache[cache_key] = result
            return result

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to get section config: {e}')
            raise

    def _parse_seat_positions(
        self, *, seat_ids: List[str], section: str, subsection: int, seats_per_row: int
    ) -> List[tuple]:
        """
        Parse seat IDs to (row, seat_num, seat_index, seat_id) format

        Accepts two formats:
        'row-seat' (e.g., '1-1')  → Requires section & subsection params
        """
        seats_to_reserve = []
        for seat_id_input in seat_ids:
            parts = seat_id_input.split('-')
            row = int(parts[0])
            seat_num = int(parts[1])
            seat_id = f'{section}-{subsection}-{row}-{seat_num}'
            seat_index = self._calculate_seat_index(row, seat_num, seats_per_row)
            seats_to_reserve.append((row, seat_num, seat_index, seat_id))

        return seats_to_reserve

    async def _verify_seats_available(
        self, *, bf_key: str, seats_to_reserve: List[tuple]
    ) -> Optional[str]:
        client = kvrocks_client.get_client()

        for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
            offset = seat_index * 2

            # Returns list with single value: [0]=AVAILABLE, [1]=RESERVED, [2]=SOLD
            result = await client.execute_command('BITFIELD', bf_key, 'GET', 'u2', offset)
            seat_status = result[0] if result else 0

            # Check if seat is AVAILABLE (0)
            if seat_status != 0:
                status = 'RESERVED' if seat_status == 1 else 'SOLD'
                return f'Seat {seat_id} is already {status}'

        return None

    # ========== Public Interface ==========

    @Logger.io
    async def reserve_seats_atomic(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        mode: str,
        section: str,
        subsection: int,
        quantity: int,
        seat_ids: Optional[List[str]] = None,
    ) -> Dict:
        with self.tracer.start_as_current_span(
            'seat_handler.reserve_atomic',
            attributes={
                'booking.id': booking_id,
            },
        ):
            if mode == 'manual':
                # Validate manual mode parameters
                if not seat_ids:
                    return self._error_result('Manual mode requires seat_ids')

                return await self._reserve_manual_seats(
                    event_id=event_id,
                    booking_id=booking_id,
                    buyer_id=buyer_id,
                    section=section,
                    subsection=subsection,
                    seat_ids=seat_ids,
                )
            elif mode == 'best_available':
                return await self._reserve_best_available_seats(
                    event_id=event_id,
                    booking_id=booking_id,
                    section=section,
                    subsection=subsection,
                    quantity=quantity,
                )
            else:
                return self._error_result(f'Invalid mode: {mode}')

    # ========== Reservation Workflows ==========

    async def _reserve_manual_seats(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        section: str,
        subsection: int,
        seat_ids: List[str],
    ) -> Dict:
        """Reserve specified seats - Manual Mode (Optimized)"""
        section_id = f'{section}-{subsection}'

        with self.tracer.start_as_current_span(
            'seat_handler.reserve_manual',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # Check idempotency first
            existing = await self.status_manager.check_booking_status(booking_id=booking_id)
            if existing:
                return existing

            try:
                # Get config and parse seats (cached after first request)
                config = await self._get_section_config(event_id=event_id, section_id=section_id)
                section_price = config['price']  # Extract price from config

                seats_to_reserve = self._parse_seat_positions(
                    seat_ids=seat_ids,
                    section=section,
                    subsection=subsection,
                    seats_per_row=config['seats_per_row'],
                )

                if not seats_to_reserve:
                    error_msg = 'No valid seats to reserve'
                    await self.status_manager.save_reservation_failure(
                        booking_id=booking_id, error_message=error_msg
                    )
                    return self._error_result(error_msg)

                # Verify availability (batch verification via pipeline)
                bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
                error = await self._verify_seats_available(
                    bf_key=bf_key, seats_to_reserve=seats_to_reserve
                )
                if error:
                    await self.status_manager.save_reservation_failure(
                        booking_id=booking_id, error_message=error
                    )
                    return self._error_result(error)

                # Execute atomic reservation (pass price to avoid redundant read)
                result = await self.reservation_executor.execute_atomic_reservation(
                    event_id=event_id,
                    section_id=section_id,
                    booking_id=booking_id,
                    bf_key=bf_key,
                    seats_to_reserve=seats_to_reserve,
                    section_price=section_price,  # Pass price to avoid redundant event_state read
                )

                return result

            except Exception as e:
                error_msg = f'Reservation error: {str(e)}'
                await self.status_manager.save_reservation_failure(
                    booking_id=booking_id, error_message=error_msg
                )
                raise

    async def _reserve_best_available_seats(
        self,
        *,
        event_id: int,
        booking_id: str,
        section: str,
        subsection: int,
        quantity: int,
    ) -> Dict:
        """Automatically find and reserve consecutive seats - Best Available Mode (Optimized)"""
        section_id = f'{section}-{subsection}'
        with self.tracer.start_as_current_span(
            'seat_handler.reserve_best_available',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # Check idempotency first
            existing = await self.status_manager.check_booking_status(booking_id=booking_id)
            if existing:
                return existing

            try:
                # Get config (cached after first request)
                config = await self._get_section_config(event_id=event_id, section_id=section_id)
                rows = config['rows']
                seats_per_row = config['seats_per_row']
                section_price = config['price']  # Extract price from config

                bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
                found_seats = await self.seat_finder.find_consecutive_seats(
                    bf_key=bf_key,
                    rows=rows,
                    seats_per_row=seats_per_row,
                    quantity=quantity,
                )

                if not found_seats:
                    error_msg = f'No {quantity} consecutive seats available'
                    await self.status_manager.save_reservation_failure(
                        booking_id=booking_id, error_message=error_msg
                    )
                    return self._error_result(error_msg)

                # Convert to reservation format
                seats_to_reserve = [
                    (row, seat_num, seat_index, f'{section}-{subsection}-{row}-{seat_num}')
                    for row, seat_num, seat_index in found_seats
                ]

                # Execute atomic reservation (pass price to avoid redundant read)
                # Total: 2 network round-trips (find + execute)
                result = await self.reservation_executor.execute_atomic_reservation(
                    event_id=event_id,
                    section_id=section_id,
                    booking_id=booking_id,
                    bf_key=bf_key,
                    seats_to_reserve=seats_to_reserve,
                    section_price=section_price,  # Pass price to avoid redundant event_state read
                )

                return result

            except Exception as e:
                error_msg = f'Reservation error: {str(e)}'
                await self.status_manager.save_reservation_failure(
                    booking_id=booking_id, error_message=error_msg
                )
                raise

    # ========== Other Command Methods ==========

    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """Release seats (RESERVED -> AVAILABLE)"""
        Logger.base.info(f'🔓 [CMD] Releasing {len(seat_ids)} seats')

        # TODO: Implement release logic
        # Hint: Similar to reserve_seats but change RESERVED -> AVAILABLE
        results = {seat_id: True for seat_id in seat_ids}
        return results

    @Logger.io
    async def finalize_payment(self, seat_id: str, event_id: int) -> bool:
        """Finalize payment (RESERVED -> SOLD)"""

        parts = seat_id.split('-')
        if len(parts) != 4:
            return False

        section, subsection, row, seat_num = parts
        section_id = f'{section}-{subsection}'

        config = await self._get_section_config(event_id, section_id)
        seats_per_row = config['seats_per_row']
        seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

        client = kvrocks_client.get_client()
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        offset = seat_index * 2

        # Set to SOLD (10): Use BITFIELD for compatibility with BITFIELD GET
        await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 2)  # 10 = SOLD
        return True

    @Logger.io
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """
        Initialize seat (set to AVAILABLE)

        Note: Price is ignored - prices are now stored in event_state JSON per section.
        This method only sets seat status to AVAILABLE in the bitfield.
        """
        parts = seat_id.split('-')
        if len(parts) != 4:
            return False

        section, subsection, row, seat_num = parts
        section_id = f'{section}-{subsection}'

        config = await self._get_section_config(event_id, section_id)
        seats_per_row = config['seats_per_row']
        seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

        client = kvrocks_client.get_client()
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        offset = seat_index * 2

        # Set to AVAILABLE (00): Use BITFIELD for compatibility with BITFIELD GET
        await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 0)  # 00 = AVAILABLE
        return True
