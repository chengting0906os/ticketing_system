"""
Create Event Use Case

Clean architecture use case for event creation:
- Uses EventTicketingAggregate as aggregate root
- Repositories manage their own atomic transactions (no UoW needed)
- Delegates infrastructure setup to orchestrator
"""

from typing import Dict

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
from src.service.ticketing.shared_kernel.domain.enum.event_status import EventStatus


class CreateEventAndTicketsUseCase:
    """
    Create Event and Tickets Use Case

    Responsibilities (Clean Architecture):
    1. Orchestrate aggregate creation (domain logic)
    2. Coordinate repository operations (each repo manages its own atomic transaction)
    3. Delegate infrastructure setup to orchestrator (separation of concerns)
    4. Handle Kvrocks initialization (fail-fast)

    Note: 不使用 UoW 的原因
    - EventTicketingCommandRepo 使用 asyncpg pool 進行批量插入（繞過 SQLAlchemy session）
    - 每個 repo 操作都是原子的（自己管理 commit/rollback）
    - 無法將 PostgreSQL + Kvrocks 包在同一個 transaction（分散式系統特性）
    - 如果 Kvrocks 失敗，PostgreSQL 已經 commit，只能透過 exception 通知上層
    """

    def __init__(
        self,
        event_ticketing_command_repo: IEventTicketingCommandRepo,
        mq_infra_orchestrator: IMqInfraOrchestrator,
        init_state_handler: IInitEventAndTicketsStateHandler,
    ):
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
    ):
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
        7. Setup MQ infrastructure (fail-safe)

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
        # 注意：此時 PostgreSQL 已經 commit，無法 rollback
        # 如果失敗，執行補償交易（刪除已創建的 event 和 tickets）
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
            # Compensating transaction: 刪除已創建的 event 和 tickets
            Logger.base.error(
                f'❌ Kvrocks initialization failed, rolling back PostgreSQL data: {e}'
            )
            try:
                await self.event_ticketing_command_repo.delete_event_aggregate(event_id=event_id)
                Logger.base.info(f'✅ Compensating transaction completed: deleted event {event_id}')
            except Exception as cleanup_error:
                Logger.base.error(f'❌ Compensating transaction failed: {cleanup_error}')
            raise  # Re-raise original exception

        # 6. Update aggregate status to AVAILABLE and persist to DB
        final_aggregate.event.status = EventStatus.AVAILABLE
        final_aggregate = await self.event_ticketing_command_repo.update_event_aggregate(
            event_aggregate=final_aggregate
        )

        Logger.base.info(
            f'✅ Created event {final_aggregate.event.id} with {len(final_aggregate.tickets)} tickets'
        )

        # 7. Setup MQ infrastructure (fail-safe - event already persisted)
        try:
            await self.mq_infra_orchestrator.setup_mq_infra(
                event_id=event_id,
                seating_config=seating_config,
            )
            Logger.base.info('✅ MQ infrastructure setup completed')

        except Exception as e:
            Logger.base.error(f'❌ MQ infrastructure setup failed: {e}')
            # Event and seats already committed - MQ failure is logged but not raised

        return final_aggregate
