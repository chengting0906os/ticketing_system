"""
Ticket Event Publisher - Handles ticket event publishing with section-based partitioning strategy
"""

from typing import List, Optional, Tuple

from src.booking.domain.domain_events import DomainEventProtocol
from src.shared.event_bus.event_publisher import publish_domain_event
from src.shared.logging.loguru_io import Logger


def _build_partition_key(*, event_id: int, section: str, subsection: int) -> str:
    """Build consistent partition key for section-based partitioning"""
    return f'{event_id}-{section}-{subsection}'


@Logger.io
async def publish_ticket_event_with_subsection_key(
    *,
    event: DomainEventProtocol,
    event_id: int,
    subsections: List[Tuple[str, int]],
    topic: Optional[str] = None,
) -> bool:
    """
    Publish ticket events using event_id + section + subsection as partition key

    Args:
        event: Domain event to publish
        event_id: Event ID
        subsections: List of affected sections and subsections (e.g., [("A", 1), ("A", 2), ("B", 1)])
        topic: Optional topic name
    """
    # Publish event once per subsection to ensure events for the same subsection are in the same partition
    for section, subsection in subsections:
        partition_key = _build_partition_key(
            event_id=event_id, section=section, subsection=subsection
        )

        Logger.base.info(
            f'Publishing event {event.__class__.__name__} for section {section}-{subsection} '
            f'with partition key: {partition_key}'
        )

        await publish_domain_event(event=event, topic=topic, partition_key=partition_key)
    return True


@Logger.io
async def publish_booking_events_by_subsections(
    *, events: List[DomainEventProtocol], event_id: int, ticket_subsections: List[Tuple[str, int]]
) -> bool:
    # Deduplicate subsection list to avoid duplicate publications
    unique_subsections = list(set(ticket_subsections))

    Logger.base.info(
        f'Publishing {len(events)} booking events for {len(unique_subsections)} '
        f'unique subsections: {unique_subsections}'
    )

    for event in events:
        await publish_ticket_event_with_subsection_key(
            event=event, event_id=event_id, subsections=unique_subsections
        )
    return True


@Logger.io
def get_subsections_from_booking_aggregate(booking_aggregate) -> List[Tuple[str, int]]:
    """
    Extract involved subsections list from BookingAggregate

    Args:
        booking_aggregate: BookingAggregate instance

    Returns:
        List of subsection tuples [(section, subsection), ...]
    """
    subsections = set()

    # Extract section and subsection information from ticket_snapshots
    for ticket_snapshot in booking_aggregate.ticket_snapshots:
        subsections.add((ticket_snapshot.section, ticket_snapshot.subsection))

    return list(subsections)


@Logger.io
async def publish_booking_created_by_subsections(
    *, booking_aggregate, topic: Optional[str] = None
) -> bool:
    subsections = get_subsections_from_booking_aggregate(booking_aggregate)

    # Get event ID
    event_id = booking_aggregate.booking.event_id

    # Publish all domain events
    await publish_booking_events_by_subsections(
        events=booking_aggregate.domain_events, event_id=event_id, ticket_subsections=subsections
    )
    return True


# Recommended Kafka Topic Configuration for ticket events
TICKET_KAFKA_CONFIG = {
    'topic_name': 'ticketing-ticket-operations',
    'partitions': 1000,  # Assuming max 100 sections x 10 subsections = 1000 total subsections
    'replication_factor': 3,
    'config': {
        'cleanup.policy': 'delete',
        'retention.ms': 86400000 * 7,  # 7 days retention
        'compression.type': 'gzip',
        'max.message.bytes': 1048576,  # 1MB max message size
    },
}
