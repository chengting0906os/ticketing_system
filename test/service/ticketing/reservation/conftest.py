"""
Pytest configuration for seat reservation tests.

SSE-related steps have been moved to test/bdd_conftest/sse_step_conftest.py.
This file contains only reservation-specific steps that aren't shared.
"""

from typing import Any

from pytest_bdd import then
from pytest_bdd.model import Step

from test.service.ticketing.reservation.fixtures import context, http_server

__all__ = [
    'context',
    'http_server',
]


# ============ Then Steps - Reservation Specific ============


@then('{ticket_type} tickets should be returned with count:')
def then_tickets_returned_with_count(
    ticket_type: str,
    step: Step,
    context: dict[str, Any],
) -> None:
    """Verify tickets are returned with correct count, optionally checking status.

    Example:
        Then available tickets should be returned with count:
          | 10 |
    """
    rows = step.data_table.rows
    expected_count = int(rows[0].cells[0].value)

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert data['total_count'] == expected_count
    assert len(data['tickets']) == expected_count

    # If ticket_type is 'available', verify all tickets have status='available'
    if ticket_type == 'available':
        for ticket in data['tickets']:
            assert ticket['status'] == 'available'
