"""
Get Section Seats Detail Use Case
Get all seat details for a specified section/subsection
"""

from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface import ISeatStateQueryHandler


class ListSectionSeatsDetailUseCase:
    """
    Get All Seat Details for Specified Section Use Case

    Responsibilities:
    - Verify section exists
    - Call Handler to get seat list
    - Calculate statistics
    """

    def __init__(self, seat_state_handler: ISeatStateQueryHandler) -> None:
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, event_id: int, section: str, subsection: int) -> dict:
        """
        Execute query

        Args:
            event_id: Event ID
            section: Section code (e.g., 'A')
            subsection: Subsection number (e.g., 1)

        Returns:
            {
                "section_id": "A-1",
                "event_id": 1,
                "section": "A",
                "subsection": 1,
                "total": 100,
                "available": 80,
                "reserved": 15,
                "sold": 5,
                "seats": [
                    {
                        "section": "A",
                        "subsection": 1,
                        "row": 1,
                        "seat_num": 1,
                        "price": 1000,
                        "status": "AVAILABLE",
                        "seat_identifier": "A-1-1-1"
                    },
                    ...
                ]
            }
        """
        from src.platform.exception.exceptions import NotFoundError

        section_id = f'{section}-{subsection}'

        # Get seat list from Handler
        seats_data = await self.seat_state_handler.list_all_subsection_seats(
            event_id=event_id, section=section, subsection=subsection
        )

        # Check if event section exists (empty list indicates not found)
        if not seats_data:
            Logger.base.warning(f'❌ [USE-CASE] Event {event_id} section {section_id} not found')
            raise NotFoundError('Event not found')

        # Calculate statistics
        total_count = len(seats_data)
        available_count = sum(1 for seat in seats_data if seat['status'] == 'available')
        reserved_count = sum(1 for seat in seats_data if seat['status'] == 'reserved')
        sold_count = sum(1 for seat in seats_data if seat['status'] == 'sold')

        Logger.base.info(
            f'✅ [USE-CASE] Section {section_id}: '
            f'total={total_count}, available={available_count}, reserved={reserved_count}, sold={sold_count}'
        )

        return {
            'section_id': section_id,
            'event_id': event_id,
            'section': section,
            'subsection': subsection,
            'total': total_count,
            'available': available_count,
            'reserved': reserved_count,
            'sold': sold_count,
            'seats': seats_data,
        }
