"""
Atomic Reservation Executor

Handles atomic seat reservation with idempotency control via booking metadata.
"""

from typing import Dict, List

from opentelemetry import trace
import orjson

from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor
from src.service.reservation.driven_adapter.state.reservation_helper.key_str_generator import (
    make_seats_bf_key,
)
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


class AtomicReservationExecutor:
    """
    Atomic Reservation Executor - Kvrocks seat reservation

    Split Methods for 5-Step Flow:
    1. execute_find_seats - Find available seats via Lua script
    2. execute_verify_seats - Verify manually selected seats via Lua script
    3. execute_update_seat_map - Update seat map in Kvrocks via Pipeline
    """

    def __init__(self, *, booking_metadata_handler: IBookingMetadataHandler) -> None:
        self.booking_metadata_handler = booking_metadata_handler
        self.tracer = trace.get_tracer(__name__)

    async def execute_find_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        rows: int,
        cols: int,
        price: int,
    ) -> Dict:
        """
        Find available seats via Lua script (Step 2 - BEST_AVAILABLE mode).

        Lua script only, no Pipeline update.
        Returns seats to reserve for downstream PostgreSQL + Pipeline steps.
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        client = kvrocks_client.get_client()

        # Execute Lua script to find consecutive seats
        lua_result = await lua_script_executor.find_consecutive_seats(
            client=client,
            keys=[bf_key],
            args=[str(rows), str(cols), str(quantity)],
        )

        if lua_result is None:
            return {
                'success': False,
                'seats_to_reserve': [],
                'total_price': 0,
                'error_message': f'No {quantity} consecutive seats available',
            }

        # Parse Lua result: {"seats": [[row, seat_num, seat_index], ...]}
        lua_data = orjson.loads(lua_result)
        found_seats = lua_data['seats']

        # Convert to reservation format: [(row, seat_num, seat_index, seat_id), ...]
        seats_to_reserve = [
            (row, seat_num, seat_index, f'{row}-{seat_num}')
            for row, seat_num, seat_index in found_seats
        ]

        return {
            'success': True,
            'seats_to_reserve': seats_to_reserve,
            'total_price': price * len(seats_to_reserve),
            'error_message': None,
        }

    async def execute_verify_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        seat_ids: List[str],
        cols: int,
        price: int,
    ) -> Dict:
        """
        Verify specified seats are available via Lua script (Step 2 - MANUAL mode).

        Lua script only, no Pipeline update.
        Returns verified seats for downstream PostgreSQL + Pipeline steps.
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        client = kvrocks_client.get_client()

        try:
            lua_result = await lua_script_executor.verify_manual_seats(
                client=client,
                keys=[bf_key],
                args=[str(cols)] + seat_ids,
            )
        except Exception as e:
            error_msg = str(e)
            # Parse Lua error format: "SEAT_UNAVAILABLE: Seat 1-5 is already RESERVED"
            if ':' in error_msg:
                error_msg = error_msg.split(':', 1)[1].strip()
            return {
                'success': False,
                'seats_to_reserve': [],
                'total_price': 0,
                'error_message': error_msg,
            }

        if lua_result is None:
            return {
                'success': False,
                'seats_to_reserve': [],
                'total_price': 0,
                'error_message': 'Lua verification returned no data',
            }

        # Parse Lua result: {"seats": [[row, seat_num, seat_index, seat_id], ...], "cols": 20}
        lua_data = orjson.loads(lua_result)
        verified_seats = lua_data['seats']

        # Convert to reservation format
        seats_to_reserve = [
            (row, seat_num, seat_index, seat_id)
            for row, seat_num, seat_index, seat_id in verified_seats
        ]

        return {
            'success': True,
            'seats_to_reserve': seats_to_reserve,
            'total_price': price * len(seats_to_reserve),
            'error_message': None,
        }

    async def execute_update_seat_map(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        seats_to_reserve: List[tuple],
        total_price: int,
    ) -> Dict:
        """
        Update seat map in Kvrocks via Pipeline (Step 4 of new flow).

        Pipeline only, no Lua script.
        Executes atomic updates: BITFIELD SET for each seat.
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        client = kvrocks_client.get_client()

        reserved_seats = []
        pipe = client.pipeline(transaction=True)

        for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
            pipe.execute_command('BITFIELD', bf_key, 'SET', 'u1', seat_index, 1)
            reserved_seats.append(seat_id)

        await pipe.execute()

        return {
            'success': True,
            'reserved_seats': reserved_seats,
            'total_price': total_price,
            'error_message': None,
        }
