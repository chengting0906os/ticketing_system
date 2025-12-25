"""
Stream Event Status Use Case

SSE streaming for real-time event status updates.
"""

from collections.abc import AsyncGenerator
from typing import Optional, Self

import anyio
from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface.i_pubsub_handler import IPubSubHandler
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate
from src.service.ticketing.domain.enum.sse_event_type import SseEventType


class StreamEventStatusUseCase:
    """Use case for streaming event status via SSE."""

    def __init__(
        self,
        event_ticketing_query_repo: IEventTicketingQueryRepo,
        pubsub_handler: IPubSubHandler,
    ) -> None:
        self.event_ticketing_query_repo = event_ticketing_query_repo
        self.pubsub_handler = pubsub_handler

    @classmethod
    @inject
    def depends(
        cls,
        event_ticketing_query_repo: IEventTicketingQueryRepo = Depends(
            Provide[Container.event_ticketing_query_repo]
        ),
        pubsub_handler: IPubSubHandler = Depends(Provide[Container.pubsub_handler]),
    ) -> Self:
        return cls(
            event_ticketing_query_repo=event_ticketing_query_repo,
            pubsub_handler=pubsub_handler,
        )

    async def get_event(self, *, event_id: int) -> Optional[EventTicketingAggregate]:
        """Get event aggregate by ID."""
        return await self.event_ticketing_query_repo.get_event_aggregate_by_id_with_tickets(
            event_id=event_id
        )

    async def stream(
        self, *, event_id: int, event_aggregate: EventTicketingAggregate
    ) -> AsyncGenerator[dict, None]:
        """
        Stream event status updates via SSE.

        Yields:
            Dict with event_type, event data, and subsection_stats
        """
        event = event_aggregate.event

        try:
            # 1. Send initial status from aggregate (same format as EventWithSubsectionStatsResponse)
            yield {
                'event_type': SseEventType.INITIAL_STATUS,
                'event_id': event_id,
                'name': event.name,
                'description': event.description,
                'seller_id': event.seller_id,
                'is_active': event.is_active,
                'status': event.status,
                'venue_name': event.venue_name,
                'seating_config': event.seating_config,
                'subsection_stats': event_aggregate.subsection_stats,
                'stats': event.stats,
            }

            # 2. Subscribe to pub/sub for updates (only send changed fields)
            async for payload in self.pubsub_handler.subscribe_event_state(event_id=event_id):
                event_state = payload.get('event_state', {})
                yield {
                    'event_type': SseEventType.STATUS_UPDATE,
                    'event_id': payload.get('event_id', event_id),
                    'stats': event_state.get('event_stats', event.stats),
                    'subsection_stats': event_state.get('subsection_stats', []),
                }

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'[SSE] Client disconnected from event {event_id}')
            raise
        except Exception as e:
            Logger.base.error(
                f'[SSE] Error in stream for event {event_id}: {type(e).__name__}: {e}'
            )
            raise
