"""
Test KVRocks Connection Pooling Implementation

Verifies that:
1. Async client uses explicit ConnectionPool with correct configuration
2. Sync client connects successfully with pool settings
"""

import pytest
from redis.asyncio import ConnectionPool as AsyncConnectionPool

from src.platform.config.core_setting import settings
from src.platform.state.kvrocks_client import KvrocksClient


class TestKvrocksClientAsyncPooling:
    """Test async client connection pooling"""

    @pytest.mark.anyio
    async def test_async_pool_is_created_and_configured(self):
        """Verify async client creates ConnectionPool with correct config"""
        client = KvrocksClient()

        try:
            redis_client = await client.connect()

            # Verify pool exists and is correct type
            assert client._pool is not None
            assert isinstance(client._pool, AsyncConnectionPool)

            # Verify pool configuration
            assert client._pool.max_connections == settings.KVROCKS_POOL_MAX_CONNECTIONS
            assert (
                client._pool.connection_kwargs['socket_timeout']
                == settings.KVROCKS_POOL_SOCKET_TIMEOUT
            )
            assert (
                client._pool.connection_kwargs['socket_connect_timeout']
                == settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT
            )
            assert (
                client._pool.connection_kwargs['socket_keepalive']
                == settings.KVROCKS_POOL_SOCKET_KEEPALIVE
            )

            # Verify client is using the pool
            assert redis_client.connection_pool == client._pool

            # Test actual operation
            await redis_client.ping()

        finally:
            await client.disconnect()
