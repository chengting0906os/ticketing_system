"""
Init Event And Tickets State Handler Implementation

Seat initialization state handler implementation - Using Pipeline for batch initialization
JSON-optimized: Config data stored as single JSON per event
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, TypedDict

import orjson
from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)
from src.service.reservation.driven_adapter.reservation_helper.row_block_manager import (
    row_block_manager,
)

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
    cols: int
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
        Generate all seat data from seating_config (compact format only).

        Format:
            {
                "rows": 1,
                "cols": 5,
                "sections": [
                    {"name": "A", "price": 3000, "subsections": 10}
                ]
            }
        """
        all_seats = []

        rows = seating_config.get('rows', 1)
        cols = seating_config.get('cols', 10)

        for section_config in seating_config['sections']:
            section_name = section_config['name']
            section_price = section_config['price']
            subsection_count = section_config['subsections']

            for subsection_num in range(1, subsection_count + 1):
                for row in range(1, rows + 1):
                    for seat_num in range(1, cols + 1):
                        seat_index = (row - 1) * cols + (seat_num - 1)
                        all_seats.append(
                            {
                                'section': section_name,
                                'subsection': subsection_num,
                                'row': row,
                                'seat_num': seat_num,
                                'seat_index': seat_index,
                                'price': section_price,
                                'rows': rows,
                                'cols': cols,
                            }
                        )

        Logger.base.info(f'📊 [INIT-HANDLER] Generated {len(all_seats)} seats from config')
        return all_seats

    @Logger.io
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: Dict) -> Dict:
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
                'event_stats': {
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
                section_name = seat['section']  # e.g., "A"
                subsection_num = str(seat['subsection'])  # e.g., "1"

                # Create section if not exists (price stored at section level)
                if section_name not in event_state['sections']:  # first time
                    event_state['sections'][section_name] = {
                        'price': seat['price'],
                        'subsections': {},
                    }

                # Create subsection if not exists (stats stored at subsection level)
                if (
                    subsection_num not in event_state['sections'][section_name]['subsections']
                ):  # first time
                    event_state['sections'][section_name]['subsections'][subsection_num] = {
                        'rows': seat['rows'],
                        'cols': seat['cols'],
                        'stats': {
                            'available': 0,
                            'reserved': 0,
                            'sold': 0,
                            'total': 0,
                            'updated_at': 0,
                        },
                    }

            timestamp = int(datetime.now(timezone.utc).timestamp())
            for section_id, total_seats in section_stats.items():
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

            # Step 4: Use Pipeline to batch write all operations
            pipe = client.pipeline()

            for seat in all_seats:
                section_id = f'{seat["section"]}-{seat["subsection"]}'
                bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
                offset = seat['seat_index'] * 2
                pipe.setbit(bf_key, offset, 0)
                pipe.setbit(bf_key, offset + 1, 0)

            event_total_seats = sum(section_stats.values())
            event_state['event_stats']['available'] = event_total_seats
            event_state['event_stats']['reserved'] = 0
            event_state['event_stats']['sold'] = 0
            event_state['event_stats']['total'] = event_total_seats
            event_state['event_stats']['updated_at'] = timestamp

            await pipe.execute()

            # Step 4.5: Initialize row_blocks for Python seat finder (A/B test)
            # Collect unique subsections and initialize each
            rows = seating_config.get('rows', 1)
            cols = seating_config.get('cols', 10)
            for section_name, section_data in event_state['sections'].items():
                for subsection_num in section_data['subsections']:
                    await row_block_manager.initialize_subsection(
                        event_id=event_id,
                        section=section_name,
                        subsection=int(subsection_num),
                        rows=rows,
                        cols=cols,
                    )

            # Step 5: Write unified event config as JSON (single key per event)
            config_key = make_event_state_key(event_id=event_id)
            event_state_json = orjson.dumps(event_state).decode()

            await client.execute_command('JSON.SET', config_key, '$', event_state_json)
            # Step 6: Verify results
            sections_count = len(event_state['sections'])
            Logger.base.info(f'✅ [INIT-HANDLER] Initialized {len(all_seats)} seats')
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
