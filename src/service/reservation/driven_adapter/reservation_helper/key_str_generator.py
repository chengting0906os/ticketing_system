"""
Key String Generator

Helper functions for generating Redis/Kvrocks keys used across the seat reservation system.
"""

import os


def _get_key_prefix() -> str:
    """Get key prefix dynamically from environment.

    This must be a function (not a module-level variable) because:
    - Module-level variables are evaluated at import time
    - pytest sets KVROCKS_KEY_PREFIX in pytest_configure, which runs AFTER module imports
    - Using a function ensures we always get the current environment value
    """
    return os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_get_key_prefix()}{key}'


def make_seats_bf_key(*, event_id: int, zone_id: str) -> str:
    """Generate bitfield key for seat status storage"""
    return _make_key(f'seats_bf:{event_id}:{zone_id}')


def make_event_state_key(*, event_id: int) -> str:
    """Generate event state key"""
    return _make_key(f'event_state:{event_id}')


def make_booking_key(*, booking_id: str) -> str:
    """Generate booking metadata key"""
    return _make_key(f'booking:{booking_id}')


def make_sellout_timer_key(*, event_id: int) -> str:
    """Generate sellout timer key"""
    return _make_key(f'event_sellout_timer:{event_id}')
