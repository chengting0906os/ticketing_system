"""
Init Event And Tickets State Handler Implementation

Seat initialization state handler implementation - Using Pipeline for batch initialization
"""

import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)


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
    - Create event_sections index and section_stats statistics
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
        2. Use Pipeline to batch write all seat bitfields and metadata
        3. Create event_sections index
        4. Create section_stats statistics

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

            # Step 3: Prepare section statistics and configurations
            section_stats: Dict[str, int] = defaultdict(int)
            section_configs: Dict[str, Dict] = {}

            # Build stats and configs from seat data
            for seat in all_seats:
                section_id = f'{seat["section"]}-{seat["subsection"]}'
                section_stats[section_id] += 1

                if section_id not in section_configs:
                    section_configs[section_id] = {
                        'rows': seat['rows'],
                        'seats_per_row': seat['seats_per_row'],
                    }

            Logger.base.info(
                f'⚙️  [INIT-HANDLER] Initializing {len(all_seats)} seats using Pipeline'
            )

            # Step 4: Use Pipeline to batch write all operations
            pipe = client.pipeline()
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))

            # Write all seat bitfields and metadata
            for seat in all_seats:
                section_id = f'{seat["section"]}-{seat["subsection"]}'
                bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
                meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{seat["row"]}')
                offset = seat['seat_index'] * 2

                # Set seat status to AVAILABLE (00)
                pipe.setbit(bf_key, offset, 0)
                pipe.setbit(bf_key, offset + 1, 0)

                # Store seat metadata (price)
                pipe.hset(meta_key, str(seat['seat_num']), str(seat['price']))

            # Create section indexes and statistics
            for section_id, total_seats in section_stats.items():
                # Add section to event's section index
                pipe.zadd(_make_key(f'event_sections:{event_id}'), {section_id: 0})

                # Initialize section statistics
                stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
                pipe.hset(
                    stats_key,
                    mapping={
                        'section_id': section_id,
                        'event_id': str(event_id),
                        'available': str(total_seats),
                        'reserved': '0',
                        'sold': '0',
                        'total': str(total_seats),
                        'updated_at': timestamp,
                    },
                )

                # Store section configuration
                config = section_configs[section_id]
                config_key = _make_key(f'section_config:{event_id}:{section_id}')
                pipe.hset(
                    config_key,
                    mapping={
                        'rows': str(config['rows']),
                        'seats_per_row': str(config['seats_per_row']),
                    },
                )

            # Execute all operations in pipeline
            await pipe.execute()

            Logger.base.info(f'✅ [INIT-HANDLER] Initialized {len(all_seats)} seats')

            # Step 5: Verify results
            sections_count = await client.zcard(_make_key(f'event_sections:{event_id}'))
            Logger.base.info(f'📋 [INIT-HANDLER] Created {sections_count} sections in index')

            return {
                'success': True,
                'total_seats': len(all_seats),
                'sections_count': int(sections_count),
                'error': None,
            }

        except Exception as e:
            error_msg = f'Seat initialization error: {str(e)}'
            Logger.base.error(f'❌ [INIT-HANDLER] {error_msg}')
            return {'success': False, 'total_seats': 0, 'sections_count': 0, 'error': error_msg}
