"""
Key String Generator

Helper functions for generating Redis/Kvrocks keys used across the seat reservation system.
"""

import os


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


def make_seats_bf_key(*, event_id: int, section_id: str) -> str:
    """Generate bitfield key for seat status storage"""
    return _make_key(f'seats_bf:{event_id}:{section_id}')


def make_event_state_key(*, event_id: int) -> str:
    """Generate event state key"""
    return _make_key(f'event_state:{event_id}')


def make_booking_key(*, booking_id: str) -> str:
    """Generate booking metadata key"""
    return _make_key(f'booking:{booking_id}')


def make_sellout_timer_key(*, event_id: int) -> str:
    """Generate sellout timer key"""
    return _make_key(f'event_sellout_timer:{event_id}')
