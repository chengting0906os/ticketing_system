from typing import Optional

from fastapi import Depends

from src.event_ticketing.port.event_schema import (
    EventAvailabilityResponse,
    EventStatusResponse,
    PriceGroup,
    SectionAvailability,
    SectionAvailabilityResponse,
    SubsectionAvailability,
    SubsectionStatus,
)
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class GetAvailabilityUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @Logger.io
    async def get_event_availability(self, *, event_id: int) -> EventAvailabilityResponse:
        """Get availability statistics for all sections of an event."""
        async with self.uow:
            # Verify event exists
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                raise NotFoundError(f'Event with id {event_id} not found')

            # Get overall event statistics
            event_stats = await self.uow.tickets.get_ticket_stats_by_event(event_id=event_id)

            # Get section-wise statistics
            sections_data = await self.uow.tickets.get_sections_with_stats(event_id=event_id)

            # Build section availability objects
            sections = []
            for section_data in sections_data:
                subsections = []
                section_totals = {'total': 0, 'available': 0, 'reserved': 0, 'sold': 0}

                for subsection_data in section_data['subsections']:
                    subsection = SubsectionAvailability(
                        subsection=subsection_data['subsection'],
                        total_tickets=subsection_data['total'],
                        available_tickets=subsection_data['available'],
                        reserved_tickets=subsection_data['reserved'],
                        sold_tickets=subsection_data['sold'],
                    )
                    subsections.append(subsection)

                    # Accumulate section totals
                    section_totals['total'] += subsection_data['total']
                    section_totals['available'] += subsection_data['available']
                    section_totals['reserved'] += subsection_data['reserved']
                    section_totals['sold'] += subsection_data['sold']

                section = SectionAvailability(
                    section=section_data['section'],
                    total_tickets=section_totals['total'],
                    available_tickets=section_totals['available'],
                    reserved_tickets=section_totals['reserved'],
                    sold_tickets=section_totals['sold'],
                    subsections=subsections,
                )
                sections.append(section)

            return EventAvailabilityResponse(
                event_id=event_id,
                total_tickets=event_stats['total'],
                available_tickets=event_stats['available'],
                reserved_tickets=event_stats['reserved'],
                sold_tickets=event_stats['sold'],
                sections=sections,
            )

    @Logger.io
    async def get_section_availability(
        self, *, event_id: int, section: str, subsection: Optional[int] = None
    ) -> SectionAvailabilityResponse:
        """Get availability statistics for a specific section or subsection."""
        async with self.uow:
            # Verify event exists
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                raise NotFoundError(f'Event with id {event_id} not found')

            if subsection is not None:
                # Get specific subsection stats
                stats = await self.uow.tickets.get_ticket_stats_by_section(
                    event_id=event_id, section=section, subsection=subsection
                )
                subsections = [
                    SubsectionAvailability(
                        subsection=subsection,
                        total_tickets=stats['total'],
                        available_tickets=stats['available'],
                        reserved_tickets=stats['reserved'],
                        sold_tickets=stats['sold'],
                    )
                ]
            else:
                # Get all subsections for the section
                sections_data = await self.uow.tickets.get_sections_with_stats(event_id=event_id)
                section_data = None
                for s in sections_data:
                    if s['section'] == section:
                        section_data = s
                        break

                if not section_data:
                    raise NotFoundError(f'Section {section} not found for event {event_id}')

                subsections = []
                section_totals = {'total': 0, 'available': 0, 'reserved': 0, 'sold': 0}

                for subsection_data in section_data['subsections']:
                    subsection_obj = SubsectionAvailability(
                        subsection=subsection_data['subsection'],
                        total_tickets=subsection_data['total'],
                        available_tickets=subsection_data['available'],
                        reserved_tickets=subsection_data['reserved'],
                        sold_tickets=subsection_data['sold'],
                    )
                    subsections.append(subsection_obj)

                    # Accumulate section totals
                    section_totals['total'] += subsection_data['total']
                    section_totals['available'] += subsection_data['available']
                    section_totals['reserved'] += subsection_data['reserved']
                    section_totals['sold'] += subsection_data['sold']

                # Update stats with calculated section totals
                stats = section_totals

            return SectionAvailabilityResponse(
                event_id=event_id,
                section=section,
                total_tickets=stats['total'],
                available_tickets=stats['available'],
                reserved_tickets=stats['reserved'],
                sold_tickets=stats['sold'],
                subsections=subsections,
            )

    @Logger.io
    async def get_event_status_with_all_subsections_tickets_count(
        self, *, event_id: int
    ) -> EventStatusResponse:
        """Get event status grouped by price with subsection details."""
        async with self.uow:
            # Verify event exists
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                raise NotFoundError(f'Event with id {event_id} not found')

            # Get sections data with stats
            sections_data = await self.uow.tickets.get_sections_with_stats(event_id=event_id)

            # Group subsections by price
            price_groups_dict = {}

            for section_data in sections_data:
                for subsection_data in section_data['subsections']:
                    subsection_num = subsection_data['subsection']
                    total_seats = subsection_data['total']
                    available_seats = subsection_data['available']

                    # Generate status text
                    if available_seats == total_seats:
                        status = 'Available'
                    else:
                        status = f'{available_seats} seat(s) remaining'

                    # Get price from seating config (we need to parse this)
                    # For now, use default prices based on subsection number
                    if subsection_num in [1, 2, 3, 4]:
                        price = 8800
                    elif subsection_num in [5, 6]:
                        price = 8000
                    else:  # 7, 8, 9, 10
                        price = 7500

                    if price not in price_groups_dict:
                        price_groups_dict[price] = []

                    price_groups_dict[price].append(
                        SubsectionStatus(
                            subsection=subsection_num,
                            total_seats=total_seats,
                            available_seats=available_seats,
                            status=status,
                        )
                    )

            # Convert to price groups list, sorted by price descending
            price_groups = []
            for price in sorted(price_groups_dict.keys(), reverse=True):
                # Sort subsections by subsection number
                subsections = sorted(price_groups_dict[price], key=lambda x: x.subsection)
                price_groups.append(PriceGroup(price=price, subsections=subsections))

            return EventStatusResponse(event_id=event_id, price_groups=price_groups)

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)
