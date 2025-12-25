"""
Init Event And Tickets State Handler Implementation

Seat initialization state handler implementation - Using Pipeline for batch initialization
PostgreSQL is the single source of truth for seating_config.
"""

from typing import Dict

import orjson
from src.service.reservation.driven_adapter.state.reservation_helper.key_str_generator import (
    make_seating_config_key,
    make_seats_bf_key,
)

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)


class InitEventAndTicketsStateHandlerImpl(IInitEventAndTicketsStateHandler):
    """
    Seat Initialization State Handler Implementation

    Responsibilities:
    - Generate all seat data from seating_config
    - Batch write bitfields to Kvrocks using Pipeline
    - Write seating_config JSON to Kvrocks (mirrors PostgreSQL)
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
            subsection_count = section_config['subsections']

            for subsection_num in range(1, subsection_count + 1):
                for row in range(1, rows + 1):
                    for seat_num in range(1, cols + 1):
                        seat_index = (row - 1) * cols + (seat_num - 1)
                        all_seats.append(
                            {
                                'section': section_name,
                                'subsection': subsection_num,
                                'seat_index': seat_index,
                            }
                        )

        Logger.base.info(f'[INIT-HANDLER] Generated {len(all_seats)} seats from config')
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

            # Step 3: Use Pipeline to batch write all bitfield operations
            pipe = client.pipeline()

            for seat in all_seats:
                section_id = f'{seat["section"]}-{seat["subsection"]}'
                bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
                # 1-bit per seat: 0=available, 1=reserved
                pipe.setbit(bf_key, seat['seat_index'], 0)

            await pipe.execute()

            # Step 4: Write seating_config JSON to Kvrocks (mirrors PostgreSQL)
            config_key = make_seating_config_key(event_id=event_id)
            seating_config_json = orjson.dumps(seating_config).decode()
            await client.execute_command('JSON.SET', config_key, '$', seating_config_json)

            # Step 5: Return result
            sections_count = len(seating_config.get('sections', []))
            Logger.base.info(f'[INIT-HANDLER] Initialized {len(all_seats)} seats')
            return {
                'success': True,
                'total_seats': len(all_seats),
                'sections_count': sections_count,
                'error': None,
            }

        except Exception as e:
            error_msg = f'Seat initialization error: {str(e)}'
            Logger.base.error(f'[INIT-HANDLER] {error_msg}')
            return {'success': False, 'total_seats': 0, 'sections_count': 0, 'error': error_msg}
