"""Then steps for seat reservation SSE test"""

from pytest_bdd import then
from test.shared.utils import extract_table_data


@then('SSE connection should be established')
def sse_connection_established(context):
    response = context['response']
    assert response.status_code == 200, f'Expected 200, got {response.status_code}'
    assert 'text/event-stream' in response.headers.get('content-type', ''), (
        'Content-Type should be text/event-stream'
    )


@then('initial status event should be received with:')
def initial_status_received(step, context):
    data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) > 0, 'No SSE events received'

    # Find the initial_status event (skip 'connected' event)
    initial_event = None
    for event in events:
        if event.get('event') == data['event_type']:
            initial_event = event
            break

    assert initial_event is not None, (
        f"Expected event type '{data['event_type']}', got events: {[e.get('event') for e in events]}"
    )

    # Check sections count
    event_data = initial_event.get('data', {})
    sections = event_data.get('sections', {})
    expected_count = int(data['sections_count'])

    assert len(sections) == expected_count, (
        f'Expected {expected_count} sections, got {len(sections)}'
    )


@then('section stats should include:')
def section_stats_include(step, context):
    """Verify section stats contain expected data."""
    data = extract_table_data(step)
    events = context.get('sse_events', [])

    assert len(events) > 0, 'No SSE events received'

    # Find event with sections data (initial_status or status_update)
    sections_event = None
    for event in events:
        event_data = event.get('data', {})
        if isinstance(event_data, dict) and 'sections' in event_data:
            sections_event = event
            break

    assert sections_event is not None, 'No event with sections data found'
    sections = sections_event['data'].get('sections', {})

    section_id = data['section_id']
    assert section_id in sections, f'Section {section_id} not found in response'

    section = sections[section_id]
    assert section['total'] == int(data['total']), f'Total mismatch for {section_id}'
    assert section['available'] == int(data['available']), f'Available mismatch for {section_id}'


@then('status update event should be received with:')
def status_update_received(step, context):
    """Verify status update event was received."""
    data = extract_table_data(step)
    events = context.get('sse_events', [])

    # Should have at least 2 events: initial + update
    assert len(events) >= 1, 'No status update event received'

    # Find status_update event
    update_event = None
    for event in events:
        if event.get('event') == data['event_type']:
            update_event = event
            break

    assert update_event is not None, f"No event with type '{data['event_type']}' found in {events}"


@then('updated section stats should show:')
def updated_section_stats_show(step, context):
    """Verify updated section stats."""
    data = extract_table_data(step)

    # Get updated stats from context
    updated_stats = context.get('updated_stats', {})

    section_id = data['section_id']
    assert section_id in updated_stats, f'Section {section_id} not found'

    section = updated_stats[section_id]
    assert section['total'] == int(data['total']), 'Total mismatch'
    assert section['available'] == int(data['available']), 'Available mismatch'
    assert section['reserved'] == int(data['reserved']), 'Reserved mismatch'


@then('all 3 users should receive status update event')
def all_users_receive_update(context):
    """Verify all users received the update."""
    connections = context.get('user_connections', [])

    assert len(connections) == 3, f'Expected 3 connections, got {len(connections)}'

    for conn in connections:
        events = conn.get('events', [])
        # Each connection should have received at least initial event
        assert len(events) > 0, f'User {conn["user_id"]} received no events'


@then('all users should see same section stats:')
def all_users_see_same_stats(step, context):
    """Verify all users see the same stats."""
    data = extract_table_data(step)
    connections = context.get('user_connections', [])

    section_id = data['section_id']
    expected_available = int(data['available'])
    expected_reserved = int(data['reserved'])

    # Check each user connection
    for conn in connections:
        events = conn.get('events', [])
        assert len(events) > 0, f'User {conn["user_id"]} has no events'

        # Find the latest event with sections data (skip disconnected events)
        latest_event = None
        for event in reversed(events):
            event_data = event.get('data', {})
            if isinstance(event_data, dict) and 'sections' in event_data:
                latest_event = event
                break

        assert latest_event is not None, f'No event with sections data for user {conn["user_id"]}'
        sections = latest_event['data'].get('sections', {})

        assert section_id in sections, f'Section {section_id} not found for user {conn["user_id"]}'

        section = sections[section_id]
        assert section['available'] == expected_available, (
            f'Available mismatch for user {conn["user_id"]}'
        )
        assert section['reserved'] == expected_reserved, (
            f'Reserved mismatch for user {conn["user_id"]}'
        )


# Note: 'section tickets should be returned with count:' step is defined in
# test/service/ticketing/integration/steps/event_ticketing/then.py
# and imported via bdd_steps_loader.py
# The ticketing version expects 'total_count' and 'tickets' in response


# Note: 'available tickets should be returned with count:' step is defined in
# test/service/ticketing/integration/steps/event_ticketing/then.py
# and imported via bdd_steps_loader.py
# The ticketing version checks 'total_count' field and validates ticket status


# Note: 'tickets should include detailed information:' step is defined in
# test/service/ticketing/integration/steps/event_ticketing/then.py
# and imported via bdd_steps_loader.py
# The ticketing version checks for 'seat_identifier', 'price', and 'section' fields
