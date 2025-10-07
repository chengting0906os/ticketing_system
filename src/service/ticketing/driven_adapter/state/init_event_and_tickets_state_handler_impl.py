"""
Init Event And Tickets State Handler Implementation

座位初始化狀態處理器實作 - 直接使用 Lua script 初始化 Kvrocks
"""

import os
from typing import Dict

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)
from src.service.ticketing.driven_adapter.state.lua_script import INITIALIZE_SEATS_SCRIPT


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


class InitEventAndTicketsStateHandlerImpl(IInitEventAndTicketsStateHandler):
    """
    座位初始化狀態處理器實作

    職責：
    - 從 seating_config 生成所有座位數據
    - 使用 Lua script 批量寫入 Kvrocks
    - 建立 event_sections 索引和 section_stats 統計
    """

    @Logger.io
    def _generate_all_seats_from_config(self, seating_config: dict, event_id: int) -> list[dict]:
        """
        從 seating_config 生成所有座位數據

        Args:
            seating_config: 座位配置，格式:
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
            event_id: 活動 ID

        Returns:
            座位列表
        """
        all_seats = []

        for section_config in seating_config['sections']:
            section_name = section_config['name']
            section_price = section_config['price']

            for subsection in section_config['subsections']:
                subsection_num = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                # 生成該 subsection 的所有座位
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
                            }
                        )

        Logger.base.info(f'📊 [INIT-HANDLER] Generated {len(all_seats)} seats from config')
        return all_seats

    @Logger.io
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: Dict) -> Dict:
        """
        從 seating_config 初始化座位（使用單一 Lua 腳本）

        Steps:
        1. 從 seating_config 生成所有座位數據
        2. 準備 Lua 腳本參數
        3. 執行 Lua 腳本批量寫入 Kvrocks
        4. 建立 event_sections 索引
        5. 建立 section_stats 統計

        Args:
            event_id: 活動 ID
            seating_config: 座位配置

        Returns:
            {
                'success': True/False,
                'total_seats': 3000,
                'sections_count': 30,
                'error': None or error message
            }
        """
        try:
            # Step 1: 生成所有座位數據
            all_seats = self._generate_all_seats_from_config(seating_config, event_id)

            if not all_seats:
                return {
                    'success': False,
                    'total_seats': 0,
                    'sections_count': 0,
                    'error': 'No seats generated from config',
                }

            # Step 2: 連接 Kvrocks
            client = await kvrocks_client.connect()

            # Step 3: 準備 Lua 腳本參數
            args = [_KEY_PREFIX, str(event_id)]

            for seat in all_seats:
                args.extend(
                    [
                        seat['section'],
                        str(seat['subsection']),
                        str(seat['row']),
                        str(seat['seat_num']),
                        str(seat['seat_index']),
                        str(seat['price']),
                    ]
                )

            Logger.base.info(f'⚙️  [INIT-HANDLER] Executing Lua script with {len(all_seats)} seats')

            # Step 4: 執行 Lua 腳本
            success_count: int = await client.eval(INITIALIZE_SEATS_SCRIPT, 0, *args)  # type: ignore[misc]

            Logger.base.info(
                f'✅ [INIT-HANDLER] Initialized {success_count}/{len(all_seats)} seats'
            )

            # Step 5: 驗證結果
            sections_count = await client.zcard(_make_key(f'event_sections:{event_id}'))
            Logger.base.info(f'📋 [INIT-HANDLER] Created {sections_count} sections in index')

            return {
                'success': True,
                'total_seats': int(success_count),
                'sections_count': int(sections_count),
                'error': None,
            }

        except Exception as e:
            error_msg = f'Seat initialization error: {str(e)}'
            Logger.base.error(f'❌ [INIT-HANDLER] {error_msg}')
            return {'success': False, 'total_seats': 0, 'sections_count': 0, 'error': error_msg}
