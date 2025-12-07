import asyncio
from typing import List, Optional, Union

from redis.asyncio import ConnectionPool as AsyncConnectionPool, Redis as AsyncRedis
from redis.asyncio.cluster import ClusterNode, RedisCluster
from redis.exceptions import RedisClusterException

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger


# Type alias for client that works in both standalone and cluster mode
KvrocksClientType = Union[AsyncRedis, RedisCluster]


def _parse_cluster_nodes(nodes_str: str) -> List[ClusterNode]:
    """
    Parse comma-separated cluster nodes string.

    Args:
        nodes_str: "host1:port1,host2:port2,host3:port3,host4:port4"

    Returns:
        List of ClusterNode objects
    """
    nodes: List[ClusterNode] = []
    for node in nodes_str.split(','):
        node = node.strip()
        if not node:
            continue
        host, port_str = node.split(':')
        nodes.append(ClusterNode(host=host, port=int(port_str)))
    return nodes


class KvrocksClient:
    """
    Async Kvrocks Client with connection pool.

    Supports both standalone and cluster mode based on settings.

    Usage:
        await kvrocks_client.initialize()  # In startup
        client = kvrocks_client.get_client()  # In handlers
    """

    def __init__(self) -> None:
        self._client: Optional[KvrocksClientType] = None
        self._is_cluster: bool = False

    async def initialize(self) -> KvrocksClientType:
        """Initialize connection pool (idempotent)"""
        if self._client is not None:
            return self._client

        if settings.KVROCKS_CLUSTER_MODE:
            self._client = await self._initialize_cluster()
            self._is_cluster = True
        else:
            self._client = await self._initialize_standalone()
            self._is_cluster = False

        return self._client

    async def _initialize_standalone(self) -> AsyncRedis:
        """Initialize standalone Redis client"""
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
        client = AsyncRedis.from_pool(pool)
        await client.ping()  # Fail-fast
        return client

    async def _initialize_cluster(self) -> RedisCluster:
        """Initialize Redis Cluster client with retry for cluster initialization"""
        if not settings.KVROCKS_CLUSTER_NODES:
            raise ValueError(
                'KVROCKS_CLUSTER_NODES must be set when KVROCKS_CLUSTER_MODE is True. '
                'Format: "host1:port1,host2:port2,host3:port3,host4:port4"'
            )

        startup_nodes = _parse_cluster_nodes(settings.KVROCKS_CLUSTER_NODES)
        max_retries = 30  # 30 retries × 2s = 60s max wait
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                client = RedisCluster(
                    startup_nodes=startup_nodes,
                    password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
                    decode_responses=settings.REDIS_DECODE_RESPONSES,
                    max_connections=settings.KVROCKS_POOL_MAX_CONNECTIONS,
                    socket_timeout=settings.KVROCKS_POOL_SOCKET_TIMEOUT,
                    socket_connect_timeout=settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT,
                    socket_keepalive=settings.KVROCKS_POOL_SOCKET_KEEPALIVE,
                    health_check_interval=settings.KVROCKS_POOL_HEALTH_CHECK_INTERVAL,
                    # Cluster-specific settings
                    require_full_coverage=True,  # All slots must be covered
                    read_from_replicas=False,  # Only read from masters for consistency
                )
                await client.ping()
                Logger.base.info('✅ KVRocks cluster connected')
                return client
            except RedisClusterException as e:
                if attempt < max_retries - 1:
                    Logger.base.warning(
                        f'⏳ Waiting for KVRocks cluster... attempt {attempt + 1}/{max_retries} | {e}'
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    raise

        # Should never reach here (last iteration raises), but makes type checker happy
        raise RedisClusterException('Failed to connect to KVRocks cluster')

    def get_client(self) -> KvrocksClientType:
        """Get Redis client (standalone or cluster)"""
        if self._client is None:
            raise RuntimeError(
                'Kvrocks client not initialized. '
                'Call await kvrocks_client.initialize() during startup.'
            )
        return self._client

    @property
    def is_cluster_mode(self) -> bool:
        """Check if running in cluster mode"""
        return self._is_cluster

    async def connect(self) -> KvrocksClientType:
        """Legacy compatibility"""
        return await self.initialize()

    async def disconnect(self) -> None:
        """Close connection pool"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._is_cluster = False


# Global singleton
kvrocks_client = KvrocksClient()
