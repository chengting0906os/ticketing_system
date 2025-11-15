"""
Seat State Command Handler Implementation

CQRS Command Side implementation for seat state management.
"""

import os
from typing import Any, Dict, List, Optional

import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.booking_status_manager import (
    BookingStatusManager,
)
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.seat_finder import (
    SeatFinder,
)
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


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

    def __init__(self, booking_metadata_handler: Optional[IBookingMetadataHandler] = None):
        # If no booking_metadata_handler provided, use default implementation
        if booking_metadata_handler is None:
            from src.service.ticketing.driven_adapter.state.booking_metadata_handler_impl import (
                BookingMetadataHandlerImpl,
            )

            booking_metadata_handler = BookingMetadataHandlerImpl()

        self.booking_metadata_handler = booking_metadata_handler
        self.status_manager = BookingStatusManager(
            booking_metadata_handler=booking_metadata_handler
        )
        self.seat_finder = SeatFinder()
        self.reservation_executor = AtomicReservationExecutor()

        # Section config cache: (event_id, section_id) -> config dict
        self._config_cache: Dict[tuple[int, str], Dict] = {}

    # ========== Helper Methods ==========

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    @staticmethod
    def _decode_int(value: Any) -> int:
        """Decode bytes/str to int, return 0 if None"""
        if not value:
            return 0
        if isinstance(value, bytes):
            return int(value.decode())
        return int(value)

    @staticmethod
    def _error_result(message: str) -> Dict:
        """Create standardized error result"""
        return {
            'success': False,
            'reserved_seats': [],
            'seat_prices': {},
            'total_price': 0,
            'subsection_stats': {},
            'event_stats': {},
            'error_message': message,
        }

    # ========== Config & Validation ==========

    @Logger.io
    async def _get_section_config(self, event_id: int, section_id: str) -> Dict:
        """
        Get section configuration from event config JSON with instance-level cache

        Section configs rarely change, so we cache them in memory to avoid repeated Kvrocks reads.
        Cache lifetime: Same as handler instance (typically request/consumer lifecycle)

        Args:
            event_id: Event ID
            section_id: Section identifier (e.g., 'A-1')

        Returns:
            Dict with 'rows', 'seats_per_row', and 'price'

        Raises:
            ValueError: If section config not found in JSON
        """
        # Check cache first
        cache_key = (event_id, section_id)
        if cache_key in self._config_cache:
            return self._config_cache[cache_key]

        # Cache miss - fetch from event config JSON
        try:
            client = kvrocks_client.get_client()
            config_key = _make_key(f'event_state:{event_id}')

            # Fetch event config JSON
            config_json = None
            Logger.base.info(f'🔍 [CONFIG-READ] Starting to fetch config for key: {config_key}')
            try:
                # Try JSON.GET first (Kvrocks native JSON support)
                # JSON.GET with $ returns a string like '[{"sections":{...}}]'
                Logger.base.info(f'🔍 [CONFIG-READ] Attempting JSON.GET for {config_key}')
                result = await client.execute_command('JSON.GET', config_key, '$')
                Logger.base.info(
                    f'🔍 [CONFIG-READ] JSON.GET succeeded, result type: {type(result)}'
                )

                if result:
                    # JSON.GET with $ returns a list like ['{"sections":{...}}']
                    # Extract the first element if it's a list
                    if isinstance(result, list) and result:
                        config_json = result[0]  # Get JSON string from list
                    elif isinstance(result, bytes):
                        config_json = result.decode()
                    else:
                        config_json = result

                    # Ensure it's a string
                    if isinstance(config_json, bytes):
                        config_json = config_json.decode()

            except Exception as e:
                Logger.base.debug(f'🔍 [CONFIG-READ] JSON.GET failed: {e}, trying fallback')
                # Fallback: Regular GET if JSON commands not supported
                try:
                    config_json = await client.get(config_key)
                    if isinstance(config_json, bytes):
                        config_json = config_json.decode()
                    Logger.base.debug(f'🔍 [CONFIG-READ] Fallback GET succeeded for {config_key}')
                except Exception as fallback_error:
                    Logger.base.error(
                        f'❌ [CONFIG-READ] Both JSON.GET and GET failed for {config_key}: {fallback_error}'
                    )
                    config_json = None

            # Parse JSON
            if config_json:
                event_state = orjson.loads(config_json)
                # If JSON.GET returned an array like [{"sections":{...}}], extract first element
                if isinstance(event_state, list) and event_state:
                    event_state = event_state[0]
            else:
                event_state = {}

            # Debug: Log what we're reading
            Logger.base.info(
                f'🔍 [CONFIG-READ] Raw config_json: {config_json[:200] if config_json else None}'
            )
            Logger.base.info(f'🔍 [CONFIG-READ] Parsed event_state: {event_state}')
            Logger.base.info(
                f'🔍 [CONFIG-READ] Event {event_id} sections in JSON: {list(event_state.get("sections", {}).keys())}'
            )
            Logger.base.info(f'🔍 [CONFIG-READ] Looking for section_id: {section_id}')
            Logger.base.info(f'🔍 [CONFIG-READ] Config key used: {config_key}')

            # Navigate hierarchical structure to get subsection config and section price
            # section_id format: "A-1" -> section "A", subsection "1"
            section_name = section_id.split('-')[0]
            subsection_num = section_id.split('-')[1]

            section_config = event_state.get('sections', {}).get(section_name, {})
            if not section_config:
                Logger.base.error(
                    f'❌ [CONFIG-READ] Section not found! Available sections: {list(event_state.get("sections", {}).keys())}, '
                    f'Requested: {section_name} (from {section_id})'
                )
                raise ValueError(f'Section config not found: {section_id}')

            subsection_config = section_config.get('subsections', {}).get(subsection_num, {})
            if not subsection_config:
                Logger.base.error(
                    f'❌ [CONFIG-READ] Subsection not found! Available subsections: {list(section_config.get("subsections", {}).keys())}, '
                    f'Requested: {subsection_num} (from {section_id})'
                )
                raise ValueError(f'Subsection config not found: {section_id}')

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
        1. Short format: 'row-seat' (e.g., '1-1')  → Requires section & subsection params
        2. Full format: 'section-subsection-row-seat' (e.g., 'A-1-1-1')
        """
        seats_to_reserve = []

        for seat_id_input in seat_ids:
            parts = seat_id_input.split('-')

            # Handle short format: 'row-seat'
            if len(parts) == 2:
                row = int(parts[0])
                seat_num = int(parts[1])
                seat_id = f'{section}-{subsection}-{row}-{seat_num}'

            # Handle full format: 'section-subsection-row-seat'
            elif len(parts) == 4:
                if parts[0] != section or int(parts[1]) != subsection:
                    Logger.base.warning(
                        f'⚠️ [CMD] Seat ID {seat_id_input} does not match section {section}-{subsection}'
                    )
                    continue
                row = int(parts[2])
                seat_num = int(parts[3])
                seat_id = seat_id_input

            else:
                Logger.base.warning(f'⚠️ [CMD] Invalid seat ID format: {seat_id_input}')
                continue

            seat_index = self._calculate_seat_index(row, seat_num, seats_per_row)
            seats_to_reserve.append((row, seat_num, seat_index, seat_id))

        return seats_to_reserve

    async def _verify_seats_available(
        self, *, bf_key: str, seats_to_reserve: List[tuple]
    ) -> Optional[str]:
        """Verify all requested seats are available"""
        client = kvrocks_client.get_client()

        for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
            offset = seat_index * 2

            # Read 2 bits for seat status
            bit1 = await client.getbit(bf_key, offset)
            bit2 = await client.getbit(bf_key, offset + 1)

            # Check if seat is AVAILABLE (00)
            if bit1 != 0 or bit2 != 0:
                status = 'RESERVED' if bit1 == 0 and bit2 == 1 else 'SOLD'
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
        seat_ids: Optional[List[str]] = None,
        section: Optional[str] = None,
        subsection: Optional[int] = None,
        quantity: Optional[int] = None,
    ) -> Dict:
        """
        Atomic seat reservation - Entry point

        Modes:
        - manual: Reserve specific seats (seat_ids required)
        - best_available: Auto-find consecutive seats (section, subsection, quantity required)
        """
        if mode == 'manual':
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
                buyer_id=buyer_id,
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
        section: Optional[str],
        subsection: Optional[int],
        seat_ids: Optional[List[str]],
    ) -> Dict:
        """Reserve specified seats - Manual Mode"""
        # Validate inputs
        if not seat_ids or not section or subsection is None:
            error_msg = 'Manual mode requires seat_ids, section, and subsection'
            await self.status_manager.save_reservation_failure(
                booking_id=booking_id, error_message=error_msg
            )
            return self._error_result(error_msg)

        # Check idempotency first
        existing = await self.status_manager.check_booking_status(booking_id=booking_id)
        if existing:
            return existing

        try:
            section_id = f'{section}-{subsection}'

            # Get config and parse seats
            config = await self._get_section_config(event_id, section_id)
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

            # Verify availability
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            error = await self._verify_seats_available(
                bf_key=bf_key, seats_to_reserve=seats_to_reserve
            )
            if error:
                await self.status_manager.save_reservation_failure(
                    booking_id=booking_id, error_message=error
                )
                return self._error_result(error)

            # Pre-fetch seat prices
            seat_prices, total_price = await self.reservation_executor.fetch_seat_prices(
                event_id=event_id,
                section_id=section_id,
                seats_to_reserve=seats_to_reserve,
            )

            # Execute atomic reservation
            result = await self.reservation_executor.execute_atomic_reservation(
                event_id=event_id,
                section_id=section_id,
                booking_id=booking_id,
                bf_key=bf_key,
                seats_to_reserve=seats_to_reserve,
                seat_prices=seat_prices,
                total_price=total_price,
            )

            # Log success with sold out indicators
            Logger.base.info(
                f'✅ [CMD] Reserved {len(result["reserved_seats"])} seats (manual), total: ${total_price}'
                f'{" 🎉 SUBSECTION SOLD OUT!" if result["subsection_stats"].get("available") == 0 else ""}'
                f'{" 🎊 EVENT SOLD OUT!" if result["event_stats"].get("available") == 0 else ""}'
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
        buyer_id: int,
        section: Optional[str],
        subsection: Optional[int],
        quantity: Optional[int],
    ) -> Dict:
        """Automatically find and reserve consecutive seats - Best Available Mode"""
        # Validate inputs
        if not section or subsection is None or not quantity:
            error_msg = 'Best available mode requires section, subsection, and quantity'
            await self.status_manager.save_reservation_failure(
                booking_id=booking_id, error_message=error_msg
            )
            return self._error_result(error_msg)

        # Check idempotency first
        existing = await self.status_manager.check_booking_status(booking_id=booking_id)
        if existing:
            return existing

        try:
            section_id = f'{section}-{subsection}'

            # Get config
            config = await self._get_section_config(event_id, section_id)
            rows = config['rows']
            seats_per_row = config['seats_per_row']

            # Find consecutive seats using SeatFinder
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            found_seats = await self.seat_finder.find_consecutive_seats(
                bf_key=bf_key, rows=rows, seats_per_row=seats_per_row, quantity=quantity
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

            # Pre-fetch seat prices
            seat_prices, total_price = await self.reservation_executor.fetch_seat_prices(
                event_id=event_id,
                section_id=section_id,
                seats_to_reserve=seats_to_reserve,
            )

            # Execute atomic reservation
            result = await self.reservation_executor.execute_atomic_reservation(
                event_id=event_id,
                section_id=section_id,
                booking_id=booking_id,
                bf_key=bf_key,
                seats_to_reserve=seats_to_reserve,
                seat_prices=seat_prices,
                total_price=total_price,
            )

            # Log success with sold out indicators
            Logger.base.info(
                f'✅ [CMD] Reserved {len(result["reserved_seats"])} consecutive seats (best_available), total: ${total_price}'
                f'{" 🎉 SUBSECTION SOLD OUT!" if result["subsection_stats"].get("available") == 0 else ""}'
                f'{" 🎊 EVENT SOLD OUT!" if result["event_stats"].get("available") == 0 else ""}'
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

        # TODO(human): Implement release logic with Lua script
        # Hint: Similar to reserve_seats but change RESERVED -> AVAILABLE
        results = {seat_id: True for seat_id in seat_ids}
        return results

    @Logger.io
    async def finalize_payment(
        self, seat_id: str, event_id: int, timestamp: Optional[str] = None
    ) -> bool:
        """Finalize payment (RESERVED -> SOLD)"""
        Logger.base.info(f'💳 [CMD] Finalizing payment for seat {seat_id}')

        try:
            parts = seat_id.split('-')
            if len(parts) != 4:
                return False

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

            client = kvrocks_client.get_client()
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            offset = seat_index * 2

            # Set to SOLD (10)
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 1)

            Logger.base.info(f'✅ [CMD] Finalized payment for {seat_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to finalize payment: {e}')
            return False

    @Logger.io
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """
        Initialize seat (set to AVAILABLE)

        Note: Price is ignored - prices are now stored in event_state JSON per section.
        This method only sets seat status to AVAILABLE in the bitfield.
        """
        Logger.base.info(f'🆕 [CMD] Initializing seat {seat_id}')

        try:
            parts = seat_id.split('-')
            if len(parts) != 4:
                return False

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

            client = kvrocks_client.get_client()
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            offset = seat_index * 2

            # Set to AVAILABLE (00)
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 0)

            # ✨ REMOVED: seat_meta Hash write (prices now in event_state JSON)

            Logger.base.info(f'✅ [CMD] Initialized seat {seat_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to initialize seat: {e}')
            return False
