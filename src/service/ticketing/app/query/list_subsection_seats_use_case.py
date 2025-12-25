from typing import Optional, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.platform.config.di import Container
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    SubsectionTicketsAggregate,
)


class ListSubsectionSeatsUseCase:
    def __init__(self, event_ticketing_query_repo: IEventTicketingQueryRepo) -> None:
        self.event_ticketing_query_repo = event_ticketing_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        event_ticketing_query_repo: IEventTicketingQueryRepo = Depends(
            Provide[Container.event_ticketing_query_repo]
        ),
    ) -> Self:
        return cls(event_ticketing_query_repo=event_ticketing_query_repo)

    async def execute(
        self, *, event_id: int, section: str, subsection: int
    ) -> Optional[SubsectionTicketsAggregate]:
        """Get subsection stats with tickets."""
        return await self.event_ticketing_query_repo.get_subsection_stats_and_tickets(
            event_id=event_id, section=section, subsection=subsection
        )
