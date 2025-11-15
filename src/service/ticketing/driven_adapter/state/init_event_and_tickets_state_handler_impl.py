"""
Init Event And Tickets State Handler Implementation

Seat initialization state handler implementation - Using Pipeline for batch initialization
JSON-optimized: Config data stored as single JSON per event
"""

from collections import defaultdict
from datetime import datetime, timezone
import os
from typing import Dict, TypedDict

import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)


class SectionStats(TypedDict):
    """Section statistics structure"""

    available: int
    reserved: int
    sold: int
    total: int
    updated_at: int


class SubsectionConfig(TypedDict):
    """Subsection configuration structure (nested under section)"""

    rows: int
    seats_per_row: int
    stats: SectionStats


class SectionConfig(TypedDict):
    """Section configuration structure (hierarchical - contains subsections)"""

    price: int  # Price at section level (not duplicated)
    subsections: Dict[str, SubsectionConfig]  # Keyed by subsection number


class EventStats(TypedDict):
    """Event-level statistics structure"""

    available: int
    reserved: int
    sold: int
    total: int
    updated_at: int


class EventConfig(TypedDict):
    """Unified event configuration structure"""

    event_stats: EventStats
    sections: Dict[str, SectionConfig]  # Keyed by section name (A, B, C, ...)


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


class InitEventAndTicketsStateHandlerImpl(IInitEventAndTicketsStateHandler):
    """
    Seat Initialization State Handler Implementation

    Responsibilities:
    - Generate all seat data from seating_config
    - Batch write to Kvrocks using Pipeline
    - Create unified event_state JSON with sections and event_stats
    """

    @Logger.io
    def _generate_all_seats_from_config(self, seating_config: dict, event_id: int) -> list[dict]:
        """
        Generate all seat data from seating_config

        Args:
            seating_config: Seat configuration, format:
                {
                    "sections": [
                        {
                            "name": "A",
                            "price": 3000,
                            "subsections": [
                                {"number": 1, "rows": 10, "seats_per_row": 10},
                                ...
                            ]
                        },
                        ...
                    ]
                }
            event_id: Event ID

        Returns:
            List of seat data dictionaries
        """
        all_seats = []

        for section_config in seating_config['sections']:
            section_name = section_config['name']
            section_price = section_config['price']

            for subsection in section_config['subsections']:
                subsection_num = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                # Generate all seats for this subsection
                for row in range(1, rows + 1):
                    for seat_num in range(1, seats_per_row + 1):
                        seat_index = (row - 1) * seats_per_row + (seat_num - 1)

                        all_seats.append(
                            {
                                'section': section_name,
                                'subsection': subsection_num,
                                'row': row,
                                'seat_num': seat_num,
                                'seat_index': seat_index,
                                'price': section_price,
                                'rows': rows,
                                'seats_per_row': seats_per_row,
                            }
                        )

        Logger.base.info(f'📊 [INIT-HANDLER] Generated {len(all_seats)} seats from config')
        return all_seats

    @Logger.io
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: Dict) -> Dict:
        """
        Initialize seats from seating_config using Pipeline for batch operations

        Steps:
        1. Generate all seat data from seating_config
        2. Build unified event_state JSON (rows, seats_per_row, price, stats per section + event_stats)
        3. Use Pipeline to batch write seat bitfields (status only)
        4. Write event_state as JSON (single key per event)

        Data Structure Changes:
        - ✅ Kept: seats_bf (bitfield for status)
        - ✅ NEW: event_state:{event_id} (JSON - unified config + section stats + event stats)
        - ❌ Removed: seat_meta (prices now per section, not per seat)
        - ❌ Removed: section_config (merged into JSON)
        - ❌ Removed: section_stats Hash (stats now in JSON)
        - ❌ Removed: event_stats Hash (stats now in JSON)
        - ❌ Removed: event_sections index (can query from JSON)

        Simplification:
        - Each section has ONE price (not per seat)
        - Reduces JSON size significantly
        - Simpler to query and maintain

        Args:
            event_id: Event ID
            seating_config: Seat configuration

        Returns:
            {
                'success': True/False,
                'total_seats': 3000,
                'sections_count': 30,
                'error': None or error message
            }
        """
        try:
            # Step 1: Generate all seat data
            all_seats = self._generate_all_seats_from_config(seating_config, event_id)

            if not all_seats:
                return {
                    'success': False,
                    'total_seats': 0,
                    'sections_count': 0,
                    'error': 'No seats generated from config',
                }

            # Step 2: Get Kvrocks client
            client = kvrocks_client.get_client()

            # Step 3: Prepare section statistics and unified event config (JSON)
            section_stats: Dict[str, int] = defaultdict(int)
            event_state: EventConfig = {
                'event_stats': {  # ✨ NEW: Event-level stats in JSON (no separate Hash)
                    'available': 0,
                    'reserved': 0,
                    'sold': 0,
                    'total': 0,
                    'updated_at': 0,
                },
                'sections': {},
            }

            # Build stats and config from seat data (hierarchical structure)
            for seat in all_seats:
                section_id = f'{seat["section"]}-{seat["subsection"]}'
                section_stats[section_id] += 1  # Track per subsection for counting

                # Extract section and subsection for hierarchical structure
                section_name = seat['section']  # e.g., "A"
                subsection_num = str(seat['subsection'])  # e.g., "1"

                # Create section if not exists (price stored at section level)
                if section_name not in event_state['sections']:
                    event_state['sections'][section_name] = {
                        'price': seat['price'],  # ✨ Price at section level (not duplicated)
                        'subsections': {},
                    }

                # Create subsection if not exists (stats stored at subsection level)
                if subsection_num not in event_state['sections'][section_name]['subsections']:
                    event_state['sections'][section_name]['subsections'][subsection_num] = {
                        'rows': seat['rows'],
                        'seats_per_row': seat['seats_per_row'],
                        'stats': {  # ✨ Stats at subsection level (replaces section_stats Hash)
                            'available': 0,  # Will be set below
                            'reserved': 0,
                            'sold': 0,
                            'total': 0,  # Will be set below
                            'updated_at': 0,  # Will be set below
                        },
                    }

            # Update stats with actual counts (navigate hierarchical structure)
            timestamp = int(datetime.now(timezone.utc).timestamp())
            for section_id, total_seats in section_stats.items():
                # Parse section_id (e.g., "A-1" -> section="A", subsection="1")
                parts = section_id.split('-')
                section_name = parts[0]
                subsection_num = parts[1]

                event_state['sections'][section_name]['subsections'][subsection_num]['stats'][
                    'available'
                ] = total_seats
                event_state['sections'][section_name]['subsections'][subsection_num]['stats'][
                    'total'
                ] = total_seats
                event_state['sections'][section_name]['subsections'][subsection_num]['stats'][
                    'updated_at'
                ] = timestamp

            # Debug: Log event_state being built
            Logger.base.info(
                f'🏗️  [INIT-HANDLER] Built event_state with sections: {list(event_state["sections"].keys())}'
            )
            Logger.base.info(f'🏗️  [INIT-HANDLER] Event config detail: {event_state}')

            Logger.base.info(
                f'⚙️  [INIT-HANDLER] Initializing {len(all_seats)} seats using Pipeline + JSON config'
            )

            # Step 4: Use Pipeline to batch write all operations
            pipe = client.pipeline()

            # Write seat bitfields (status only - prices moved to JSON)
            for seat in all_seats:
                section_id = f'{seat["section"]}-{seat["subsection"]}'
                bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
                offset = seat['seat_index'] * 2

                # Set seat status to AVAILABLE (00)
                pipe.setbit(bf_key, offset, 0)
                pipe.setbit(bf_key, offset + 1, 0)

            event_total_seats = sum(section_stats.values())
            event_state['event_stats']['available'] = event_total_seats
            event_state['event_stats']['reserved'] = 0
            event_state['event_stats']['sold'] = 0
            event_state['event_stats']['total'] = event_total_seats
            event_state['event_stats']['updated_at'] = timestamp

            # ✨ REMOVED: event_stats Hash (stats now in event_state JSON)

            Logger.base.info(
                f'📊 [INIT-HANDLER] Event-level stats: total={event_total_seats} seats across {len(section_stats)} subsections'
            )

            # Execute all operations in pipeline
            await pipe.execute()

            Logger.base.info(f'✅ [INIT-HANDLER] Initialized {len(all_seats)} seats')

            # Step 5: Write unified event config as JSON (single key per event)
            config_key = _make_key(f'event_state:{event_id}')
            event_state_json = orjson.dumps(event_state).decode()

            try:
                # Try JSON.SET first (Kvrocks native JSON support)
                await client.execute_command('JSON.SET', config_key, '$', event_state_json)
                Logger.base.info(
                    f'✅ [INIT-HANDLER] Saved event config as JSON (native): {config_key}'
                )
            except Exception as e:
                # Fallback: Store as regular string if JSON commands not supported
                Logger.base.warning(
                    f'⚠️  [INIT-HANDLER] JSON.SET not supported, using fallback: {e}'
                )
                await client.set(config_key, event_state_json)
                Logger.base.info(f'✅ [INIT-HANDLER] Saved event config as string: {config_key}')

            # Step 6: Verify results
            sections_count = len(event_state['sections'])
            Logger.base.info(f'📋 [INIT-HANDLER] Created {sections_count} sections in event_state')

            return {
                'success': True,
                'total_seats': len(all_seats),
                'sections_count': sections_count,
                'error': None,
            }

        except Exception as e:
            error_msg = f'Seat initialization error: {str(e)}'
            Logger.base.error(f'❌ [INIT-HANDLER] {error_msg}')
            return {'success': False, 'total_seats': 0, 'sections_count': 0, 'error': error_msg}
