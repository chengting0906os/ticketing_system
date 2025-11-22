"""
Lua Scripts for Redis/Kvrocks

Simplified approach using redis-py's built-in register_script().
"""

from pathlib import Path
from typing import Any

from redis.asyncio import Redis

from src.platform.logging.loguru_io import Logger


class LuaScripts:
    """Manages Lua scripts using redis-py's register_script()"""

    def __init__(self) -> None:
        self._find_consecutive_seats_script: Any = None
        self._initialized: bool = False

    async def initialize(self, *, client: Redis) -> None:
        """Load Lua scripts (idempotent)"""
        if self._initialized:
            return

        # Load find_consecutive_seats.lua from seat_reservation service
        project_root = Path(__file__).parent.parent.parent
        script_path = (
            project_root
            / 'service'
            / 'seat_reservation'
            / 'driven_adapter'
            / 'seat_reservation_helper'
            / 'lua_scripts'
            / 'find_consecutive_seats.lua'
        )
        if not script_path.exists():
            Logger.base.warning(f'⚠️ [LUA] Script not found: {script_path}')
            self._initialized = True
            return

        script_content = script_path.read_text()
        self._find_consecutive_seats_script = client.register_script(script_content)
        self._initialized = True

    async def find_consecutive_seats(
        self, *, client: Redis, keys: list[str], args: list[str]
    ) -> Any:
        """Execute find_consecutive_seats Lua script"""
        if self._find_consecutive_seats_script is None:
            raise RuntimeError('Lua scripts not initialized')

        return await self._find_consecutive_seats_script(keys=keys, args=args, client=client)


# Global singleton
lua_script_executor = LuaScripts()
