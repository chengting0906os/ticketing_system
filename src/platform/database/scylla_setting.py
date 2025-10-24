"""
ScyllaDB connection pool management

This module provides async ScyllaDB operations using scylla-driver
with connection pooling optimized for ScyllaDB's shard-per-core architecture.

Multi-Event-Loop Support:
- Maintains separate sessions per event loop
- Supports concurrent services (FastAPI + MQ Consumer)
- Prevents "session was closed" errors from event loop mismatch

Usage:
    session = await get_scylla_session()
    result = await session.execute_async("SELECT * FROM users WHERE id = ?", [user_id])
"""

import asyncio

from cassandra import ConsistencyLevel
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile, Session
from cassandra.query import SimpleStatement

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger


# Global sessions per event loop
scylla_sessions: dict[int, Session] = {}


def _create_cluster() -> Cluster:
    """
    Create ScyllaDB cluster with optimized configuration

    Configuration:
    - Shard-aware routing: Automatically routes requests to correct shard
    - Token-aware policy: Minimizes network hops by routing to replica
    - WhiteList policy: Prevents Docker internal IP discovery (localhost-only for tests)
    - Connection pooling: One connection per shard for optimal performance
    - Authentication: Uses username/password from settings
    - Execution Profiles: Define consistency, timeout, and load balancing per profile

    Returns:
        Cluster: Configured ScyllaDB cluster
    """
    from cassandra.auth import PlainTextAuthProvider
    from cassandra.policies import ExponentialReconnectionPolicy, WhiteListRoundRobinPolicy

    # Use WhiteList to prevent auto-discovery of Docker internal IPs
    # This ensures tests only connect to localhost, not 172.22.0.x Docker IPs
    load_balancing_policy = WhiteListRoundRobinPolicy(settings.SCYLLA_CONTACT_POINTS)

    # Authentication
    auth_provider = PlainTextAuthProvider(
        username=settings.SCYLLA_USERNAME, password=settings.SCYLLA_PASSWORD.get_secret_value()
    )

    # Create execution profile for default operations
    # This replaces the deprecated session-level settings (consistency_level, timeout)
    # Note: load_balancing_policy must be in the profile, not in Cluster() when using profiles
    default_profile = ExecutionProfile(
        load_balancing_policy=load_balancing_policy,
        consistency_level=ConsistencyLevel.LOCAL_QUORUM,
        request_timeout=settings.SCYLLA_REQUEST_TIMEOUT,
        # Note: retry_policy defaults to RetryPolicy() which is sufficient for most cases
        # DowngradingConsistencyRetryPolicy is deprecated and should be avoided
    )

    return Cluster(
        contact_points=settings.SCYLLA_CONTACT_POINTS,
        port=settings.SCYLLA_PORT,
        auth_provider=auth_provider,
        protocol_version=4,  # CQL native protocol v4
        compression=True,  # Enable LZ4 compression
        # Connection pooling (one per shard for optimal performance)
        executor_threads=8,  # Thread pool size for async operations
        # Timeouts
        connect_timeout=settings.SCYLLA_CONNECT_TIMEOUT,
        control_connection_timeout=settings.SCYLLA_CONTROL_TIMEOUT,
        # Retry and reconnection
        reconnection_policy=ExponentialReconnectionPolicy(base_delay=1, max_delay=30),
        # Execution profiles (replaces deprecated session-level settings)
        execution_profiles={EXEC_PROFILE_DEFAULT: default_profile},
    )


async def get_scylla_session() -> Session:
    """
    Get or create ScyllaDB session for the current event loop

    Session lifecycle management:
    - One session per event loop to prevent connection errors
    - Session reuse across requests within same event loop
    - Automatic connection pooling (one connection per shard)

    Returns:
        Session: ScyllaDB session for async operations
    """
    current_loop = asyncio.get_running_loop()
    loop_id = id(current_loop)

    # Fast path: session already exists for this loop
    if loop_id in scylla_sessions:
        session = scylla_sessions[loop_id]
        Logger.base.debug(f'♻️  [ScyllaDB] Reusing session (loop={loop_id})')
        return session

    # Slow path: create new session (should only happen at startup)
    Logger.base.info(f'🔌 [ScyllaDB] Creating new session (loop={loop_id})...')

    cluster = _create_cluster()
    # Support pytest-xdist worker isolation: read keyspace from environment
    import os

    keyspace = os.getenv('SCYLLA_KEYSPACE', settings.SCYLLA_KEYSPACE)
    session = await asyncio.to_thread(cluster.connect, keyspace)

    # Note: Consistency level and timeout are now configured via execution profiles
    # in _create_cluster() instead of session-level settings (which are deprecated)

    scylla_sessions[loop_id] = session

    Logger.base.info(f'✅ [ScyllaDB] Session created (loop={loop_id}, keyspace={keyspace})')

    return scylla_sessions[loop_id]


async def close_scylla_session():
    """
    Close the ScyllaDB session for the current event loop

    Note: Only closes the session for the current event loop.
    Other event loops' sessions remain active.
    """
    current_loop = asyncio.get_running_loop()
    loop_id = id(current_loop)

    if loop_id in scylla_sessions:
        session = scylla_sessions[loop_id]
        await asyncio.to_thread(session.cluster.shutdown)
        del scylla_sessions[loop_id]
        Logger.base.info(f'🔌 [ScyllaDB] Session closed (loop={loop_id})')


async def close_all_scylla_sessions():
    """
    Close all ScyllaDB sessions across all event loops

    Warning: Only call this during application shutdown.
    Do not call from within an active event loop that has connections.
    """
    for loop_id, session in list(scylla_sessions.items()):
        try:
            await asyncio.to_thread(session.cluster.shutdown)
            Logger.base.info(f'🔌 [ScyllaDB] Session closed (loop={loop_id})')
        except Exception as e:
            Logger.base.error(f'❌ [ScyllaDB] Error closing session (loop={loop_id}): {e}')
    scylla_sessions.clear()


async def warmup_scylla_session() -> bool:
    """
    Warmup ScyllaDB session by establishing connections to all shards

    This eliminates "connect" latency during request handling by forcing
    the session to establish connections at startup time.

    Returns:
        bool: True if warmup succeeded
    """
    try:
        Logger.base.info('🔥 [ScyllaDB Warmup] Starting warmup...')

        session = await get_scylla_session()

        # Execute a simple query to force connection establishment
        query = SimpleStatement(
            'SELECT * FROM system.local', consistency_level=ConsistencyLevel.ONE
        )

        await asyncio.to_thread(session.execute, query)

        Logger.base.info('✅ [ScyllaDB Warmup] Completed: connections ready')
        return True

    except Exception as e:
        Logger.base.error(f'❌ [ScyllaDB Warmup] Failed: {e}')
        return False
