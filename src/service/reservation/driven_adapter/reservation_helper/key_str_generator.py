"""
Key String Generator - Redis Cluster Compatible

Helper functions for generating Redis/Kvrocks keys with hash tags for cluster routing.

Redis Cluster Hash Tag Strategy:
- Hash tag {content} determines which slot (0-16383) a key routes to
- All keys with same hash tag go to the same slot/node
- Subsection-level keys: {e:EVENT_ID:ss:SUBSECTION_ID} - Co-locate seats + booking
- Event-level keys: {e:EVENT_ID} - Co-locate event state + timers

Slot Distribution (4 nodes, 16384 slots):
- Node 1: slots 0-4095
- Node 2: slots 4096-8191
- Node 3: slots 8192-12287
- Node 4: slots 12288-16383
"""

import os


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_subsection_hash_tag(*, event_id: int, section: str, subsection: int) -> str:
    """
    Generate hash tag for subsection-level keys.

    Format: {e:EVENT_ID:ss:SECTION-SUBSECTION}
    Ensures seats_bf and booking for same subsection go to same slot.

    Args:
        event_id: Event identifier
        section: Section name (e.g., 'A', 'B')
        subsection: Subsection number (e.g., 1, 2)

    Example: {e:1:ss:A-1}
    """
    return f'{{e:{event_id}:ss:{section}-{subsection}}}'


def _make_event_hash_tag(*, event_id: int) -> str:
    """
    Generate hash tag for event-level keys.

    Format: {e:EVENT_ID}
    Ensures event_state and sellout_timer for same event go to same slot.

    Example: {e:1}
    """
    return f'{{e:{event_id}}}'


def make_seats_bf_key(*, event_id: int, section: str, subsection: int) -> str:
    """
    Generate bitfield key for seat status storage.

    Format: [PREFIX]{e:EVENT_ID:ss:SECTION-SUBSECTION}:seats_bf
    Uses subsection hash tag for cluster co-location with booking keys.

    Args:
        event_id: Event identifier
        section: Section name (e.g., 'A', 'B')
        subsection: Subsection number (e.g., 1, 2)

    Example: {e:1:ss:A-1}:seats_bf
    """
    hash_tag = _make_subsection_hash_tag(event_id=event_id, section=section, subsection=subsection)
    return f'{_KEY_PREFIX}{hash_tag}:seats_bf'


def make_event_state_key(*, event_id: int) -> str:
    """
    Generate event state key.

    Format: [PREFIX]{e:EVENT_ID}:event_state
    Uses event hash tag for cluster routing.

    Example: {e:1}:event_state
    """
    hash_tag = _make_event_hash_tag(event_id=event_id)
    return f'{_KEY_PREFIX}{hash_tag}:event_state'


def make_booking_key(*, booking_id: str, event_id: int, section: str, subsection: int) -> str:
    """
    Generate booking metadata key with hash tag for cluster co-location.

    Format: [PREFIX]{e:EVENT_ID:ss:SECTION-SUBSECTION}:booking:BOOKING_ID
    Uses subsection hash tag to co-locate with seats_bf for atomic operations.

    Args:
        booking_id: UUID7 booking identifier
        event_id: Event identifier
        section: Section name (e.g., 'A', 'B')
        subsection: Subsection number (e.g., 1, 2)

    Example: {e:1:ss:A-1}:booking:019af799-ec16-73b2-b160-d24ae18b5942
    """
    hash_tag = _make_subsection_hash_tag(event_id=event_id, section=section, subsection=subsection)
    return f'{_KEY_PREFIX}{hash_tag}:booking:{booking_id}'


def make_sellout_timer_key(*, event_id: int) -> str:
    """
    Generate sellout timer key.

    Format: [PREFIX]{e:EVENT_ID}:sellout_timer
    Uses event hash tag for cluster routing.

    Example: {e:1}:sellout_timer
    """
    hash_tag = _make_event_hash_tag(event_id=event_id)
    return f'{_KEY_PREFIX}{hash_tag}:sellout_timer'
