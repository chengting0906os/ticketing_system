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

            # Verify client is stored (production client uses single _client)
            assert client._client is not None
            assert client._client == redis_client

            # Verify pool exists and is correct type
            pool = redis_client.connection_pool
            assert pool is not None
            assert isinstance(pool, AsyncConnectionPool)

            # Verify pool configuration
            assert pool.max_connections == settings.KVROCKS_POOL_MAX_CONNECTIONS
            assert pool.connection_kwargs['socket_timeout'] == settings.KVROCKS_POOL_SOCKET_TIMEOUT
            assert (
                pool.connection_kwargs['socket_connect_timeout']
                == settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT
            )
            assert (
                pool.connection_kwargs['socket_keepalive'] == settings.KVROCKS_POOL_SOCKET_KEEPALIVE
            )

            # Test actual operation
            await redis_client.ping()

        finally:
            await client.disconnect()
