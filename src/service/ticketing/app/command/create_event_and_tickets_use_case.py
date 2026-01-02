"""
Create Event Use Case

Clean architecture use case for event creation:
- Uses EventTicketingAggregate as aggregate root
- Repositories manage their own atomic transactions (no UoW needed)
- Delegates infrastructure setup to orchestrator
"""

from typing import Dict, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    IEventTicketingCommandRepo,
)
from src.service.ticketing.app.interface.i_init_event_and_tickets_state_handler import (
    IInitEventAndTicketsStateHandler,
)
from src.service.ticketing.app.interface.i_mq_infra_orchestrator import IMqInfraOrchestrator
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
)
from src.service.ticketing.domain.enum.event_status import EventStatus


class CreateEventAndTicketsUseCase:
    def __init__(
        self,
        event_ticketing_command_repo: IEventTicketingCommandRepo,
        mq_infra_orchestrator: IMqInfraOrchestrator,
        init_state_handler: IInitEventAndTicketsStateHandler,
    ) -> None:
        self.event_ticketing_command_repo = event_ticketing_command_repo
        self.mq_infra_orchestrator = mq_infra_orchestrator
        self.init_state_handler = init_state_handler

    @classmethod
    @inject
    def depends(
        cls,
        event_ticketing_command_repo: IEventTicketingCommandRepo = Depends(
            Provide[Container.event_ticketing_command_repo]
        ),
        mq_infra_orchestrator: IMqInfraOrchestrator = Depends(
            Provide[Container.mq_infra_orchestrator]
        ),
        init_state_handler: IInitEventAndTicketsStateHandler = Depends(
            Provide[Container.init_event_and_tickets_state_handler]
        ),
    ) -> Self:
        return cls(
            event_ticketing_command_repo=event_ticketing_command_repo,
            mq_infra_orchestrator=mq_infra_orchestrator,
            init_state_handler=init_state_handler,
        )

    @Logger.io
    async def create_event_and_tickets(
        self,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> EventTicketingAggregate:
        """
        Create event with tickets and setup infrastructure.

        Flow:
        1. Create aggregate (domain)
        2. Persist event to DB (atomic, repo commits)
        3. Batch insert tickets to DB (atomic, repo commits)
        4. Extract event_id (fail-fast check)
        5. Initialize seats in Kvrocks (fail-fast with compensating transaction)
        6. Update status to AVAILABLE in DB (atomic, repo commits)
        7. Setup Kafka topics and partitions (fail-safe, auto-creates if fails)

        Args:
            name: Event name
            description: Event description
            seller_id: Seller ID
            venue_name: Venue name
            seating_config: Seat configuration
            is_active: Whether event is active

        Returns:
            Created EventTicketingAggregate

        Raises:
            Exception: If seat initialization fails
        """

        # 1. Create aggregate (domain logic)
        event_aggregate = EventTicketingAggregate.create_event_with_tickets(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
        )

        # 2. Persist event to get ID (atomic transaction in repo)
        saved_aggregate = await self.event_ticketing_command_repo.create_event_aggregate(
            event_aggregate=event_aggregate
        )

        # 3. Generate tickets for batch insert
        ticket_tuples = saved_aggregate.generate_tickets()
        Logger.base.info(f'Prepared {len(ticket_tuples)} tickets for batch insert')

        # 4. Batch insert tickets (atomic transaction in repo)
        final_aggregate = (
            await self.event_ticketing_command_repo.create_event_aggregate_with_batch_tickets(
                event_aggregate=saved_aggregate,
                ticket_tuples=ticket_tuples,
            )
        )

        # Extract event_id for later use
        event_id = final_aggregate.event.id
        if not event_id:
            raise Exception('Event ID is missing after creation')

        # 5. Initialize seats in Kvrocks (fail-fast with compensating transaction)
        # Note: At this point PostgreSQL has already committed, cannot rollback
        # If failed, execute compensating transaction (delete created event and tickets)
        try:
            result = await self.init_state_handler.initialize_seats_from_config(  # raw sql
                event_id=event_id,
                seating_config=seating_config,
            )

            if not result['success']:
                raise Exception(f'Seat initialization failed: {result["error"]}')

            Logger.base.info(
                f'✅ Seats initialized: {result["total_seats"]} seats, {result["sections_count"]} sections'
            )

        except Exception as e:
            # Compensating transaction: delete created event and tickets
            Logger.base.error(
                f'❌ Kvrocks initialization failed, rolling back PostgreSQL data: {e}'
            )
            try:
                await self.event_ticketing_command_repo.delete_event_aggregate(event_id=event_id)
                Logger.base.info(f'✅ Compensating transaction completed: deleted event {event_id}')
            except Exception as cleanup_error:
                Logger.base.error(f'❌ Compensating transaction failed: {cleanup_error}')
            raise  # Re-raise original exception

        # 6. Update event status to AVAILABLE
        await self.event_ticketing_command_repo.update_event_status(
            event_id=event_id,
            status=EventStatus.AVAILABLE.value,
        )
        final_aggregate.event.status = EventStatus.AVAILABLE

        # 7. Setup Kafka topics and partitions (fail-safe)
        try:
            await self.mq_infra_orchestrator.setup_kafka_topics_and_partitions(
                event_id=event_id,
                seating_config=seating_config,
            )
        except Exception as e:
            # Kafka setup failure should not block event creation
            # Topics will be auto-created when first message is sent
            Logger.base.warning(f'⚠️ Kafka setup failed, will auto-create on first use: {e}')

        Logger.base.info(
            f'✅ Created event {final_aggregate.event.id} with {len(final_aggregate.tickets)} tickets'
        )

        return final_aggregate
