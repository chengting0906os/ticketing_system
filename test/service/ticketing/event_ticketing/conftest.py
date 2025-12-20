"""
BDD Step Definitions for Event Ticketing Tests

Contains Given/When/Then steps for:
- Event creation and listing
- Ticket auto-creation
- Seating config validation
- Compensating transactions
- SSE seat status streaming

Note: SSE fixtures (http_server, async_client) are in test/service/ticketing/fixtures.py
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
import orjson
import pytest
from pytest_bdd import given, then
from pytest_bdd.model import Step

from src.platform.constant.route_constant import EVENT_BASE
from test.constants import (
    DEFAULT_PASSWORD,
    EMPTY_LIST_SELLER_EMAIL,
    EMPTY_LIST_SELLER_NAME,
    LIST_SELLER_EMAIL,
    LIST_TEST_SELLER_NAME,
)
from test.bdd_conftest.shared_step_utils import (
    create_user,
    extract_table_data,
    login_user,
)


# =============================================================================
# Helper Functions
# =============================================================================


def _create_seller_and_events(
    *,
    step: Step,
    client: TestClient,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
    seller_email: str,
    seller_name: str,
    force_status_update: bool = False,
) -> None:
    """Create seller and events from step table.

    Args:
        force_status_update: If True, always update status. If False, only update if not 'available'.
    """
    created_user = create_user(client, seller_email, DEFAULT_PASSWORD, seller_name, 'seller')
    seller_id = created_user['id'] if created_user else 1
    context['seller_id'] = seller_id
    context['created_events'] = []
    login_user(client, seller_email, DEFAULT_PASSWORD)

    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        request_json = {
            'name': event_data['name'],
            'description': event_data['description'],
            'is_active': event_data['is_active'].lower() == 'true',
        }
        if 'venue_name' in event_data:
            request_json['venue_name'] = event_data['venue_name']
        if 'seating_config' in event_data:
            request_json['seating_config'] = orjson.loads(event_data['seating_config'])

        create_response = client.post(EVENT_BASE, json=request_json)
        if create_response.status_code == 201:
            created_event = create_response.json()
            event_id = created_event['id']
            should_update = force_status_update or event_data['status'] != 'available'
            if should_update:
                execute_sql_statement(
                    'UPDATE event SET status = :status WHERE id = :id',
                    {'status': event_data['status'], 'id': event_id},
                )
                created_event['status'] = event_data['status']
            context['created_events'].append(created_event)


# =============================================================================
# Given Steps
# =============================================================================


@given('a seller with events:')
def create_seller_with_events(
    step: Step,
    client: TestClient,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> None:
    _create_seller_and_events(
        step=step,
        client=client,
        context=context,
        execute_sql_statement=execute_sql_statement,
        seller_email=LIST_SELLER_EMAIL,
        seller_name=LIST_TEST_SELLER_NAME,
        force_status_update=False,
    )


@given('no available events exist')
def create_no_available_events(
    step: Step,
    client: TestClient,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> None:
    _create_seller_and_events(
        step=step,
        client=client,
        context=context,
        execute_sql_statement=execute_sql_statement,
        seller_email=EMPTY_LIST_SELLER_EMAIL,
        seller_name=EMPTY_LIST_SELLER_NAME,
        force_status_update=True,
    )


@given('Kvrocks seat initialization will fail')
def mock_kvrocks_failure(request: pytest.FixtureRequest) -> None:
    """
    Mock Kvrocks initialization to fail, testing compensating transaction.

    This simulates a distributed system failure scenario where:
    1. PostgreSQL commits successfully
    2. Kvrocks initialization fails
    3. Compensating transaction should delete PostgreSQL data
    """

    async def failing_init(*args: object, **kwargs: object) -> dict[str, object]:
        """Mock initialization that always fails"""
        return {
            'success': False,
            'error': 'Simulated Kvrocks connection failure',
            'total_seats': 0,
            'sections_count': 0,
        }

    # Patch the init_state_handler to return failure
    mock_patcher = patch(
        'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl'
        '.InitEventAndTicketsStateHandlerImpl.initialize_seats_from_config',
        new=failing_init,
    )

    mock_patcher.start()

    # Register cleanup to stop the patcher after test
    request.addfinalizer(mock_patcher.stop)


# =============================================================================
# Then Steps
# =============================================================================
# Note: "an event exists with:" step is defined in test/given_step_conftest.py


@then('the event should be created with:')
def verify_event_created(step: Step, context: dict[str, Any]) -> None:
    expected_data = extract_table_data(step)
    response = context['response']
    response_json = response.json()
    for field, expected_value in expected_data.items():
        if expected_value == '{any_int}':
            assert field in response_json, f"Response should contain field '{field}'"
            assert isinstance(response_json[field], int), f'{field} should be an integer'
            assert response_json[field] > 0, f'{field} should be positive'
        elif field == 'is_active':
            expected_active = expected_value.lower() == 'true'
            assert response_json['is_active'] == expected_active
        elif field == 'status':
            assert response_json['status'] == expected_value
        elif field in ['seller_id', 'id']:
            assert response_json[field] == int(expected_value)
        elif field == 'seating_config':
            # Handle JSON comparison for seating_config
            expected_json = orjson.loads(expected_value)
            assert response_json[field] == expected_json, (
                f'seating_config mismatch: expected {expected_json}, got {response_json[field]}'
            )
        else:
            assert response_json[field] == expected_value


def _verify_event_count(context: dict[str, Any], count: int) -> list[dict[str, Any]]:
    response = context['response']
    assert response.status_code == 200, (
        f'Expected status 200, got {response.status_code}: {response.text}'
    )
    events = response.json()
    assert len(events) == count, f'Expected {count} events, got {len(events)}'
    return events


@then('the seller should see 5 events')
def verify_seller_sees_5_events(context: dict[str, Any]) -> None:
    _verify_event_count(context, 5)


@then('the buyer should see 2 events')
def verify_buyer_sees_2_events(context: dict[str, Any]) -> None:
    events = _verify_event_count(context, 2)
    for p in events:
        assert p['is_active'] is True
        assert p['status'] == 'available'


@then('the buyer should see 0 events')
def verify_buyer_sees_0_events(context: dict[str, Any]) -> None:
    _verify_event_count(context, 0)


@then('the events should include all statuses')
def verify_events_include_all_statuses(context: dict[str, Any]) -> None:
    response = context['response']
    events = response.json()
    statuses = {event['status'] for event in events}
    expected_statuses = {'available', 'sold_out', 'completed'}
    assert expected_statuses.issubset(statuses), (
        f'Expected statuses {expected_statuses}, got {statuses}'
    )


@then('the events should be:')
def verify_specific_events(step: Step, context: dict[str, Any]) -> None:
    response = context['response']
    events = response.json()
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    expected_events = []
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_events.append(dict(zip(headers, values, strict=True)))
    assert len(events) == len(expected_events), (
        f'Expected {len(expected_events)} events, got {len(events)}'
    )
    for expected in expected_events:
        found = False
        for event in events:
            if event['name'] == expected['name']:
                assert event['description'] == expected['description']
                # Price is no longer part of event - it's on tickets
                assert str(event['is_active']).lower() == expected['is_active'].lower()
                assert event['status'] == expected['status']
                found = True
                break
        assert found, f'Event {expected["name"]} not found in response'


@then('tickets should be auto-created with:')
def verify_tickets_auto_created(
    step: Step, context: dict[str, Any], execute_sql_statement: Callable[..., list[dict[str, Any]]]
) -> None:
    """Verify that tickets were automatically created in PostgreSQL after event creation."""
    expected_data = extract_table_data(step)

    # Get the created event
    event = context.get('event')
    if not event:
        raise AssertionError('Event not found in context')

    event_id = event['id']

    # Query tickets directly from PostgreSQL (source of truth for tickets)
    tickets = execute_sql_statement(
        'SELECT * FROM ticket WHERE event_id = :event_id', {'event_id': event_id}, fetch=True
    )

    # Verify ticket count
    expected_count = int(expected_data['count'])
    assert len(tickets) == expected_count, (
        f'Expected {expected_count} tickets in DB, got {len(tickets)}'
    )

    # Verify ticket prices (if specified)
    if 'price' in expected_data:
        expected_price = int(expected_data['price'])
        for ticket in tickets:
            assert ticket['price'] == expected_price, (
                f'Expected ticket price {expected_price}, got {ticket["price"]}'
            )

    # Verify ticket status
    expected_status = expected_data['status']
    for ticket in tickets:
        assert ticket['status'] == expected_status, (
            f'Expected ticket status {expected_status}, got {ticket["status"]}'
        )


@then('the event should not exist in database:')
def verify_event_not_exists(
    step: Step, execute_sql_statement: Callable[..., list[dict[str, Any]]]
) -> None:
    """
    Verify that event does not exist in database (compensating transaction worked).

    This validates that after Kvrocks failure, the compensating transaction
    successfully deleted the event from PostgreSQL.
    """
    expected_data = extract_table_data(step)
    event_name = expected_data['name']

    # Query database for event with this name
    result = execute_sql_statement(
        'SELECT id, name FROM event WHERE name = :name',
        {'name': event_name},
        fetch=True,
    )

    # Result should be empty list (no matching events)
    assert not result or len(result) == 0, (
        f'Event "{event_name}" should NOT exist in database after compensating transaction, '
        f'but found: {result}'
    )


@then('no tickets should exist for this event')
def verify_no_tickets_exist(execute_sql_statement: Callable[..., list[dict[str, Any]]]) -> None:
    """
    Verify that no tickets exist for the failed event.

    Validates that compensating transaction cleaned up both event AND tickets.
    Since event creation failed, check that NO tickets exist for "Doomed%" events.
    """
    # Check that NO tickets exist for any event created in this test
    result = execute_sql_statement(
        'SELECT COUNT(*) as count FROM ticket WHERE event_id IN '
        '(SELECT id FROM event WHERE name LIKE :pattern)',
        {'pattern': 'Doomed%'},
        fetch=True,
    )

    ticket_count = result[0]['count'] if result else 0

    assert ticket_count == 0, f'Expected 0 tickets for failed event, but found {ticket_count}'


@then('the database should be in consistent state')
def verify_database_consistency(execute_sql_statement: Callable[..., list[dict[str, Any]]]) -> None:
    """
    Verify overall database consistency after compensating transaction.

    Checks:
    1. No orphaned tickets (tickets without corresponding events)
    2. All events have matching ticket counts
    """
    # Check for orphaned tickets
    orphaned_tickets = execute_sql_statement(
        'SELECT COUNT(*) as count FROM ticket t '
        'WHERE NOT EXISTS (SELECT 1 FROM event e WHERE e.id = t.event_id)',
        {},
        fetch=True,
    )

    orphan_count = orphaned_tickets[0]['count'] if orphaned_tickets else 0

    assert orphan_count == 0, f'Found {orphan_count} orphaned tickets (tickets without events)'


@then('{ticket_type} tickets should be returned with count:')
def then_tickets_returned_with_count(
    ticket_type: str,
    step: Step,
    context: dict[str, Any],
) -> None:
    """Verify tickets are returned with correct count, optionally checking status.

    Note: tickets field contains SeatResponse objects grouped by status.
    Each SeatResponse has seat_positions list with individual seat positions.

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

    # Count total seat_positions across all SeatResponse groups
    total_seats = sum(len(ticket['seat_positions']) for ticket in data['tickets'])
    assert total_seats == expected_count, (
        f'Expected {expected_count} total seats, got {total_seats}'
    )

    # If ticket_type is 'available', verify all tickets have status='available'
    if ticket_type == 'available':
        for ticket in data['tickets']:
            assert ticket['status'] == 'available', (
                f"Expected status 'available', got '{ticket['status']}'"
            )


@then('all subsection stats should be returned:')
def then_all_subsection_stats_returned(
    step: Step,
    context: dict[str, Any],
) -> None:
    """Verify all subsection stats are returned with correct values.

    Response format (from Kvrocks):
        {
            "event_id": 1,
            "sections": {
                "A-1": {"available": 50, "reserved": 0, "sold": 0, "total": 50},
                "A-2": {"available": 50, "reserved": 0, "sold": 0, "total": 50},
                ...
            },
            "total_sections": 4
        }

    Example:
        Then all subsection stats should be returned:
          | section | subsection | total | available |
          | A       | 1          | 50    | 50        |
    """
    response = context['response']
    assert response.status_code == 200

    data = response.json()
    sections = data.get('sections', {})

    # Parse expected data from step table
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    expected_stats = []
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        row_data = dict(zip(headers, values, strict=True))
        expected_stats.append(
            {
                'section': row_data['section'],
                'subsection': int(row_data['subsection']),
                'total': int(row_data['total']),
                'available': int(row_data['available']),
            }
        )

    # Verify each expected subsection
    for expected in expected_stats:
        # Build key like "A-1" from section="A" and subsection=1
        section_key = f'{expected["section"]}-{expected["subsection"]}'
        assert section_key in sections, (
            f'Section {section_key} not found in response. Available: {list(sections.keys())}'
        )

        section_stats = sections[section_key]
        assert section_stats['total'] == expected['total'], (
            f'Section {section_key}: expected total={expected["total"]}, got {section_stats["total"]}'
        )
        assert section_stats['available'] == expected['available'], (
            f'Section {section_key}: expected available={expected["available"]}, '
            f'got {section_stats["available"]}'
        )
