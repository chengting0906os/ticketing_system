"""
Lua Scripts for Redis/Kvrocks

Simplified approach using redis-py's built-in register_script().
"""

from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import NoScriptError

from src.platform.logging.loguru_io import Logger


class LuaScripts:
    """Manages Lua scripts using redis-py's register_script()"""

    def __init__(self) -> None:
        self._find_consecutive_seats_script: Any = None
        self._verify_manual_seats_script: Any = None
        self._find_and_reserve_seats_script: Any = None
        self._find_consecutive_seats_source: str = ''
        self._verify_manual_seats_source: str = ''
        self._find_and_reserve_seats_source: str = ''
        self._initialized: bool = False

    async def initialize(self, *, client: Redis) -> None:
        """Load Lua scripts (idempotent)"""
        if self._initialized:
            return

        project_root = Path(__file__).parent.parent.parent
        lua_scripts_dir = (
            project_root
            / 'service'
            / 'reservation'
            / 'driven_adapter'
            / 'reservation_helper'
            / 'lua_scripts'
        )

        # Load find_consecutive_seats.lua
        find_seats_path = lua_scripts_dir / 'find_consecutive_seats.lua'
        if find_seats_path.exists():
            self._find_consecutive_seats_source = find_seats_path.read_text()
            self._find_consecutive_seats_script = client.register_script(
                self._find_consecutive_seats_source
            )
        else:
            Logger.base.warning(f'⚠️ [LUA] Script not found: {find_seats_path}')

        # Load verify_manual_seats.lua
        verify_seats_path = lua_scripts_dir / 'verify_manual_seats.lua'
        if verify_seats_path.exists():
            self._verify_manual_seats_source = verify_seats_path.read_text()
            self._verify_manual_seats_script = client.register_script(
                self._verify_manual_seats_source
            )
        else:
            Logger.base.warning(f'⚠️ [LUA] Script not found: {verify_seats_path}')

        # Load find_and_reserve_seats.lua (atomic find + reserve)
        find_and_reserve_path = lua_scripts_dir / 'find_and_reserve_seats.lua'
        if find_and_reserve_path.exists():
            self._find_and_reserve_seats_source = find_and_reserve_path.read_text()
            self._find_and_reserve_seats_script = client.register_script(
                self._find_and_reserve_seats_source
            )
        else:
            Logger.base.warning(f'⚠️ [LUA] Script not found: {find_and_reserve_path}')

        self._initialized = True

    async def find_consecutive_seats(
        self, *, client: Redis, keys: list[str], args: list[str]
    ) -> bytes | None:
        """Execute find_consecutive_seats Lua script with auto-retry on NoScriptError"""
        if self._find_consecutive_seats_script is None:
            raise RuntimeError('Lua scripts not initialized')

        try:
            return await self._find_consecutive_seats_script(keys=keys, args=args, client=client)
        except NoScriptError:
            Logger.base.warning('⚠️ [LUA] find_consecutive_seats not found, re-registering...')
            self._find_consecutive_seats_script = client.register_script(
                self._find_consecutive_seats_source
            )
            result = await self._find_consecutive_seats_script(keys=keys, args=args, client=client)
            return result  # pyrefly: ignore

    async def verify_manual_seats(
        self, *, client: Redis, keys: list[str], args: list[str]
    ) -> bytes | None:
        """Execute verify_manual_seats Lua script with auto-retry on NoScriptError"""
        if self._verify_manual_seats_script is None:
            raise RuntimeError('Lua scripts not initialized')

        try:
            return await self._verify_manual_seats_script(keys=keys, args=args, client=client)
        except NoScriptError:
            Logger.base.warning('⚠️ [LUA] verify_manual_seats not found, re-registering...')
            self._verify_manual_seats_script = client.register_script(
                self._verify_manual_seats_source
            )
            result = await self._verify_manual_seats_script(keys=keys, args=args, client=client)
            return result  # pyrefly: ignore

    async def find_and_reserve_seats(
        self, *, client: Redis, keys: list[str], args: list[str]
    ) -> bytes | None:
        """Execute find_and_reserve_seats Lua script (atomic find + reserve) with auto-retry"""
        if self._find_and_reserve_seats_script is None:
            raise RuntimeError('Lua scripts not initialized')

        try:
            return await self._find_and_reserve_seats_script(keys=keys, args=args, client=client)
        except NoScriptError:
            Logger.base.warning('⚠️ [LUA] find_and_reserve_seats not found, re-registering...')
            self._find_and_reserve_seats_script = client.register_script(
                self._find_and_reserve_seats_source
            )
            result = await self._find_and_reserve_seats_script(keys=keys, args=args, client=client)
            return result  # pyrefly: ignore


# Global singleton
lua_script_executor = LuaScripts()
