"""
Test-only Kvrocks Client

Extends production KvrocksClient to support per-event-loop connections
for pytest-asyncio (which creates new loop per test function).

Production code stays simple - test complexity isolated here.
"""

import asyncio

from redis import Redis as SyncRedis
from redis.asyncio import ConnectionPool as AsyncConnectionPool, Redis as AsyncRedis

from src.platform.config.core_setting import settings
from src.platform.state.kvrocks_client import KvrocksClient


class KvrocksTestClientAsync(KvrocksClient):
    """
    Test-specific async Kvrocks client with per-event-loop support.

    Overrides production client to handle pytest-asyncio's
    per-function event loops (asyncio_default_fixture_loop_scope = "function").
    """

    def __init__(self) -> None:
        super().__init__()
        self._clients: dict[int, AsyncRedis] = {}

    async def initialize(self) -> AsyncRedis:
        """Initialize connection pool for current event loop"""
        loop_id = id(asyncio.get_running_loop())

        if loop_id in self._clients:
            return self._clients[loop_id]

        pool = AsyncConnectionPool.from_url(
            f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            max_connections=settings.KVROCKS_POOL_MAX_CONNECTIONS,
            socket_timeout=settings.KVROCKS_POOL_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=settings.KVROCKS_POOL_SOCKET_KEEPALIVE,
            health_check_interval=settings.KVROCKS_POOL_HEALTH_CHECK_INTERVAL,
        )
        self._clients[loop_id] = AsyncRedis.from_pool(pool)
        await self._clients[loop_id].ping()

        return self._clients[loop_id]

    def get_client(self) -> AsyncRedis:
        """Get Redis client for current event loop (auto-initializes if needed)"""
        loop_id = id(asyncio.get_running_loop())

        if loop_id not in self._clients:
            raise RuntimeError(
                'Kvrocks test client not initialized for current event loop. '
                f'Loop ID: {loop_id}. Available loops: {list(self._clients.keys())}. '
                'This typically happens when FastAPI TestClient runs in a different event loop. '
                'The app lifespan initializes the client, but TestClient may use a sync context.'
            )

        return self._clients[loop_id]

    async def disconnect(self) -> None:
        """Close connection for current event loop"""
        loop_id = id(asyncio.get_running_loop())
        if client := self._clients.pop(loop_id, None):
            await client.aclose()

    async def disconnect_all(self) -> None:
        """Close all connections"""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


class KvrocksTestClientSync:
    """
    Synchronous Kvrocks client for test cleanup.

    Isolated from production code - used only in test fixtures
    to clean test data without async/event-loop complications.
    """

    def __init__(self) -> None:
        self._client: SyncRedis | None = None

    def connect(self) -> SyncRedis:
        """Establish Kvrocks connection (sync version)"""
        if self._client is None:
            self._client = SyncRedis.from_url(
                f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
                password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
                decode_responses=settings.REDIS_DECODE_RESPONSES,
                max_connections=settings.KVROCKS_POOL_MAX_CONNECTIONS,
                socket_timeout=settings.KVROCKS_POOL_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=settings.KVROCKS_POOL_SOCKET_KEEPALIVE,
                health_check_interval=settings.KVROCKS_POOL_HEALTH_CHECK_INTERVAL,
            )
        return self._client

    def disconnect(self) -> None:
        """Close Kvrocks connection"""
        if self._client:
            self._client.close()
            self._client = None

    @property
    def client(self) -> SyncRedis:
        """Get Redis client (sync version)"""
        if self._client is None:
            raise RuntimeError('Kvrocks test client not connected. Call connect() first.')
        return self._client


# Test-specific singletons
kvrocks_client_async_for_test = KvrocksTestClientAsync()
kvrocks_test_client = KvrocksTestClientSync()
