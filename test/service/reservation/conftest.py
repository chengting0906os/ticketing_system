"""
Pytest configuration for seat reservation tests.

Re-exports shared fixtures from test/service/reservation/fixtures.py
"""

from test.service.reservation.fixtures import context, http_server


__all__ = [
    'context',
    'http_server',
]
