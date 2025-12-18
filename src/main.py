"""
Production FastAPI Application

Full application with Kafka consumers, Redis Pub/Sub, and background tasks.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from src.platform.app_factory import create_app
from src.platform.config.di import container
from src.platform.config.wire_modules import WIRE_MODULES
from src.platform.database.asyncpg_setting import (
    close_all_asyncpg_pools,
    get_asyncpg_pool,
    warmup_asyncpg_pool,
)
from src.platform.database.orm_db_setting import get_engine
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import close_producer
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor
from src.service.ticketing.driven_adapter.state.real_time_event_state_subscriber import (
    RealTimeEventStateSubscriber,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage unified application lifespan: startup and shutdown."""
    Logger.base.info('🚀 [Unified Service] Starting up...')

    # Setup OpenTelemetry tracing (environment-aware: Jaeger local, X-Ray AWS)
    tracing = TracingConfig(service_name='ticketing-service')
    tracing.setup()
    Logger.base.info('📊 [Unified Service] OpenTelemetry tracing configured')

    # Wire dependency injection for all modules
    container.wire(modules=WIRE_MODULES)
    Logger.base.info('🔌 [Unified Service] Dependency injection wired')

    # Initialize database
    engine = get_engine()
    if engine and tracing:
        tracing.instrument_sqlalchemy(engine=engine)
        Logger.base.info('🗄️  [Unified Service] Database engine ready + instrumented')

    # Auto-instrument Redis/Kvrocks
    if tracing:
        tracing.instrument_redis()
        Logger.base.info('📊 [Unified Service] Redis instrumentation configured')

    # Initialize Kvrocks connection pool (fail-fast)
    client = await kvrocks_client.initialize()
    Logger.base.info('📡 [Unified Service] Kvrocks initialized')

    # Initialize Lua scripts
    await lua_script_executor.initialize(client=client)
    Logger.base.info('🔥 [Unified Service] Lua scripts loaded')

    # Initialize asyncpg connection pool (eager initialization)
    await get_asyncpg_pool()
    Logger.base.info('🏊 [Unified Service] Asyncpg pool initialized')

    # Warmup pool to eliminate "connect" spans during request handling
    await warmup_asyncpg_pool()
    Logger.base.info('🔥 [Unified Service] Asyncpg pool warmed up to MIN_SIZE')

    # Get event ID from environment for consumer topic initialization
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create Kafka topics before consumers start
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(f'📝 [Unified Service] Kafka topics ensured for EVENT_ID={event_id}')

    Logger.base.info('✅ [Unified Service] All services initialized')

    # Create task group for background tasks (Redis Pub/Sub subscriber)
    async with anyio.create_task_group() as tg:
        seat_availability_cache = container.seat_availability_query_handler()
        redis_subscriber = RealTimeEventStateSubscriber(
            event_id=event_id, cache_handler=seat_availability_cache
        )
        await redis_subscriber.start(task_group=tg)
        Logger.base.info('✅ [Ticketing Service] Ready to serve requests with real-time cache')

        yield

        Logger.base.info('🛑 [Unified Service] Shutting down...')
        tg.cancel_scope.cancel()

    # Flush and close Kafka producer before shutdown
    try:
        await close_producer()
        Logger.base.info('📤 [Unified Service] Kafka producer closed')
    except Exception as e:
        Logger.base.error(f'❌ [Unified Service] Failed to close Kafka producer: {e}')

    # Close asyncpg pools
    await close_all_asyncpg_pools()
    Logger.base.info('🏊 [Unified Service] Asyncpg pools closed')

    # Disconnect Kvrocks
    await kvrocks_client.disconnect()
    Logger.base.info('📡 [Unified Service] Kvrocks disconnected')

    # Shutdown tracing (flush remaining spans)
    if tracing:
        tracing.shutdown()
        Logger.base.info('📊 [Unified Service] Tracing shutdown complete')

    # Unwire DI
    container.unwire()

    Logger.base.info('👋 [Unified Service] Shutdown complete')


# Create FastAPI app using shared factory
app = create_app(
    lifespan=lifespan,
    description='Unified Ticketing System - Handles user authentication, event management, booking, and seat reservation',
)

Logger.base.info('📊 [Unified Service] FastAPI auto-instrumentation enabled')


@app.get('/')
async def root() -> RedirectResponse:
    """Root endpoint - redirect to docs."""
    return RedirectResponse(url='/docs')
