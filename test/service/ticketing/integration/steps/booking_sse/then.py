"""Then steps for booking SSE feature tests"""

import re

from pytest_bdd import then

from test.shared.utils import extract_table_data


@then('booking SSE connection should be established')
def booking_sse_connection_established(context):
    """Verify booking SSE connection is successfully established"""
    response = context['response']
    assert response.status_code == 200, f'Expected 200, got {response.status_code}'
    assert 'text/event-stream' in response.headers.get('content-type', ''), (
        'Content-Type should be text/event-stream'
    )


@then('booking initial status event should be received with:')
def booking_initial_status_event_received(step, context):
    """Verify booking initial status event is received with correct data"""
    expected_data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) > 0, 'No SSE events received'

    # Find the initial_status event
    initial_event = None
    for event in events:
        if event.get('event') == expected_data['event_type']:
            initial_event = event
            break

    assert initial_event is not None, (
        f"Expected event type '{expected_data['event_type']}', got events: {[e.get('event') for e in events]}"
    )

    # Verify event data
    event_data = initial_event.get('data', {})
    assert event_data.get('booking_id') == expected_data['booking_id']
    assert event_data.get('status') == expected_data['status']

    # Store event for further assertions
    context['last_event'] = initial_event


@then('status update event should be received with:')
def status_update_event_received(step, context):
    """Verify status update event is received with correct data"""
    expected_data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) > 0, 'No SSE events received'

    # Find the event matching expected event_type
    matching_event = None
    for event in events:
        if event.get('event') == expected_data['event_type']:
            matching_event = event
            break

    assert matching_event is not None, (
        f"No event with type '{expected_data['event_type']}' found in {events}"
    )

    # Verify status in event data
    event_data = matching_event.get('data', {})
    if 'status' in expected_data:
        assert event_data.get('status') == expected_data['status'], (
            f"Expected status '{expected_data['status']}', got '{event_data.get('status')}'"
        )

    # Store event for further assertions
    context['last_event'] = matching_event


@then('the event should include seat details:')
def event_includes_seat_details(step, context):
    """Verify event includes seat reservation details"""
    expected_data = extract_table_data(step)
    event = context.get('last_event', {})
    event_data = event.get('data', {})

    assert event_data, 'No event data found'

    if 'details' in event_data:
        details = event_data['details']
        if 'reserved_seats' in expected_data:
            assert details['reserved_seats'] == expected_data['reserved_seats'].split(',')
        if 'total_price' in expected_data:
            assert details['total_price'] == int(expected_data['total_price'])
    else:
        if 'reserved_seats' in expected_data:
            assert event_data['reserved_seats'] == expected_data['reserved_seats'].split(',')
        if 'total_price' in expected_data:
            assert event_data['total_price'] == int(expected_data['total_price'])


@then('the event should include error message:')
def event_includes_error_message(step, context):
    """Verify event includes error message"""
    expected_data = extract_table_data(step)
    event = context.get('last_event', {})
    event_data = event.get('data', {})

    if 'details' in event_data:
        assert 'error_message' in event_data['details']
        assert expected_data['error_message'] in event_data['details']['error_message']
    else:
        assert 'error_message' in event_data
        assert expected_data['error_message'] in event_data['error_message']


@then('the event should include payment details:')
def event_includes_payment_details(step, context):
    """Verify event includes payment details"""
    expected_data = extract_table_data(step)
    event = context.get('last_event', {})
    event_data = event.get('data', {})

    details = event_data.get('details', event_data)

    # Check payment_id (may be mock format)
    if 'payment_id' in expected_data:
        expected_pattern = expected_data['payment_id']
        if '*' in expected_pattern:
            # Pattern matching (e.g., "PAY_MOCK_*")
            pattern = expected_pattern.replace('*', '.*')
            assert re.match(pattern, details['payment_id']), (
                f"Payment ID {details['payment_id']} doesn't match pattern {expected_pattern}"
            )
        else:
            assert details['payment_id'] == expected_pattern

    # Check paid_at timestamp
    if 'paid_at' in expected_data:
        expected_pattern = expected_data['paid_at']
        if '*' in expected_pattern:
            # Just check it exists and is a timestamp
            assert 'paid_at' in details
            assert isinstance(details['paid_at'], str)
        else:
            assert details['paid_at'] == expected_pattern


@then('the event should include cancellation timestamp')
def event_includes_cancellation_timestamp(context):
    """Verify event includes cancellation timestamp"""
    event = context.get('last_event', {})
    event_data = event.get('data', {})
    details = event_data.get('details', event_data)

    assert 'cancelled_at' in details
    assert isinstance(details['cancelled_at'], str)
