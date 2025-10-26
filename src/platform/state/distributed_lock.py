"""
Distributed Lock using Kvrocks (Redis)

Simple distributed lock implementation using Redis SET NX EX command.
"""

from typing import Optional
from uuid import uuid4

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client


class DistributedLock:
    """
    分散式鎖實作

    使用 Redis SET NX EX 實現簡單的分散式鎖
    """

    def __init__(self):
        self.lock_value: Optional[str] = None

    async def acquire_lock(self, *, key: str, ttl: int = 10) -> bool:
        """
        獲取分散式鎖

        Args:
            key: Lock key (e.g., "lock:event:123:subsection:A-1")
            ttl: Time-to-live in seconds (default: 10s)

        Returns:
            True if lock acquired, False otherwise
        """
        client = kvrocks_client.get_client()
        self.lock_value = str(uuid4())  # Unique value for ownership verification

        try:
            # SET key value NX EX ttl
            # NX: Only set if not exists (atomic)
            # EX: Set expiry time in seconds
            result = await client.set(
                key,
                self.lock_value,
                nx=True,  # Only set if not exists
                ex=ttl,  # Expiry time
            )

            if result:
                Logger.base.debug(f'🔒 [LOCK] Acquired lock: {key} (ttl={ttl}s)')
                return True
            else:
                Logger.base.debug(f'⏳ [LOCK] Failed to acquire lock: {key} (already locked)')
                return False

        except Exception as e:
            Logger.base.error(f'❌ [LOCK] Error acquiring lock {key}: {e}')
            return False

    async def release_lock(self, *, key: str) -> bool:
        """
        釋放分散式鎖

        使用 Lua script 確保只釋放自己持有的鎖 (ownership check)

        Args:
            key: Lock key

        Returns:
            True if lock released, False otherwise
        """
        if not self.lock_value:
            Logger.base.warning(f'⚠️ [LOCK] No lock value to release: {key}')
            return False

        client = kvrocks_client.get_client()

        try:
            # Lua script to verify ownership before deleting
            # This ensures we only delete our own lock
            release_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            result = await client.eval(release_script, 1, key, self.lock_value)  # type: ignore

            if result:
                Logger.base.debug(f'🔓 [LOCK] Released lock: {key}')
                return True
            else:
                Logger.base.warning(
                    f'⚠️ [LOCK] Failed to release lock: {key} (ownership mismatch or expired)'
                )
                return False

        except Exception as e:
            Logger.base.error(f'❌ [LOCK] Error releasing lock {key}: {e}')
            return False
        finally:
            self.lock_value = None
