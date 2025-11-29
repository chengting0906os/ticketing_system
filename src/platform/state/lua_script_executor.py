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
        self._verify_manual_seats_script: Any = None
        self._initialized: bool = False

    async def initialize(self, *, client: Redis) -> None:
        """Load Lua scripts (idempotent)"""
        if self._initialized:
            return

        project_root = Path(__file__).parent.parent.parent
        lua_scripts_dir = (
            project_root
            / 'service'
            / 'seat_reservation'
            / 'driven_adapter'
            / 'seat_reservation_helper'
            / 'lua_scripts'
        )

        # Load find_consecutive_seats.lua
        find_seats_path = lua_scripts_dir / 'find_consecutive_seats.lua'
        if find_seats_path.exists():
            self._find_consecutive_seats_script = client.register_script(
                find_seats_path.read_text()
            )
        else:
            Logger.base.warning(f'⚠️ [LUA] Script not found: {find_seats_path}')

        # Load verify_manual_seats.lua
        verify_seats_path = lua_scripts_dir / 'verify_manual_seats.lua'
        if verify_seats_path.exists():
            self._verify_manual_seats_script = client.register_script(verify_seats_path.read_text())
        else:
            Logger.base.warning(f'⚠️ [LUA] Script not found: {verify_seats_path}')

        self._initialized = True

    async def find_consecutive_seats(
        self, *, client: Redis, keys: list[str], args: list[str]
    ) -> Any:
        """Execute find_consecutive_seats Lua script"""
        if self._find_consecutive_seats_script is None:
            raise RuntimeError('Lua scripts not initialized')

        return await self._find_consecutive_seats_script(keys=keys, args=args, client=client)

    async def verify_manual_seats(self, *, client: Redis, keys: list[str], args: list[str]) -> Any:
        """Execute verify_manual_seats Lua script"""
        if self._verify_manual_seats_script is None:
            raise RuntimeError('Lua scripts not initialized')

        return await self._verify_manual_seats_script(keys=keys, args=args, client=client)


# Global singleton
lua_script_executor = LuaScripts()
