"""
Seat Availability Query Use Case
Get real-time seat status from Kvrocks, combined with basic information from PostgreSQL
"""

from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.interface import ISeatStateQueryHandler


class ListAllSubSectionStatusUseCase:
    """
    Seat Availability Query Use Case

    Get statistics for all sections from Kvrocks
    """

    def __init__(self, seat_state_handler: ISeatStateQueryHandler) -> None:
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, *, event_id: int) -> dict:
        """
        Get statistics for all sections of an event (read from Kvrocks)

        Optimization strategy:
        1. Query Kvrocks directly (independent service, can skip queue)
        2. Kvrocks persistence at the bottom layer (zero data loss)
        3. Expected performance: ~10-30ms (querying 100 sections, Pipeline optimized)
        4. Not affected by Kafka backlog

        Args:
            event_id: Event ID

        Returns:
            {
                "event_id": 1,
                "sections": {
                    "A-1": {"available": 100, "reserved": 20, "sold": 30, "total": 150},
                    ...
                },
                "total_sections": 100
            }
        """
        # Use SeatStateHandler to get statistics
        all_sections = await self.seat_state_handler.list_all_subsection_status(event_id=event_id)

        Logger.base.info(
            f'📊 [USE-CASE] Retrieved {len(all_sections)} sections for event {event_id}'
        )

        return {'event_id': event_id, 'sections': all_sections, 'total_sections': len(all_sections)}
