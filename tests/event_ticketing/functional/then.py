from pytest_bdd import then

from tests.shared.utils import extract_single_value, extract_table_data


@then('the event should be created with:')
def verify_event_created(step, event_state=None, context=None):
    import json

    # Import the helper function from shared
    from tests.shared.then import get_state_with_response

    expected_data = extract_table_data(step)
    state = get_state_with_response(event_state=event_state, context=context)
    response = state['response']
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
            expected_json = json.loads(expected_value)
            assert response_json[field] == expected_json, (
                f'seating_config mismatch: expected {expected_json}, got {response_json[field]}'
            )
        else:
            assert response_json[field] == expected_value


def _verify_error_contains(event_state, expected_text):
    response = event_state['response']
    response_json = response.json()
    error_msg = str(response_json)
    assert expected_text in error_msg, (
        f"Expected '{expected_text}' in error message, got: {error_msg}"
    )


def _verify_event_count(event_state, count):
    response = event_state['response']
    assert response.status_code == 200
    events = response.json()
    assert len(events) == count, f'Expected {count} events, got {len(events)}'
    return events


@then('the seller should see 5 events')
def verify_seller_sees_5_events(event_state):
    _verify_event_count(event_state, 5)


@then('the buyer should see 2 events')
def verify_buyer_sees_2_events(event_state):
    events = _verify_event_count(event_state, 2)
    for p in events:
        assert p['is_active'] is True
        assert p['status'] == 'available'


@then('the buyer should see 0 events')
def verify_buyer_sees_0_events(event_state):
    _verify_event_count(event_state, 0)


@then('the events should include all statuses')
def verify_events_include_all_statuses(event_state):
    response = event_state['response']
    events = response.json()
    statuses = {event['status'] for event in events}
    expected_statuses = {'available', 'sold_out'}
    assert expected_statuses.issubset(statuses), (
        f'Expected statuses {expected_statuses}, got {statuses}'
    )


@then('the events should be:')
def verify_specific_events(step, event_state):
    response = event_state['response']
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
def verify_tickets_auto_created(step, client, context):
    """Verify that tickets were automatically created after event creation."""
    from src.shared.constant.route_constant import EVENT_TICKETS_BY_SUBSECTION

    expected_data = extract_table_data(step)

    # Get the created event
    event = context.get('event')
    if not event:
        raise AssertionError('Event not found in context')

    # Get tickets for the event
    event_id = event['id']
    response = client.get(EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id))
    assert response.status_code == 200, f'Failed to get tickets: {response.text}'

    tickets_data = response.json()
    tickets = tickets_data.get('tickets', [])

    # Verify ticket count
    expected_count = int(expected_data['count'])
    assert len(tickets) == expected_count, f'Expected {expected_count} tickets, got {len(tickets)}'

    # Verify ticket prices (tickets can have different prices based on section)
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


@then('tickets should be returned with count:')
def tickets_returned_with_count(step, context):
    """Verify tickets are returned with correct count."""
    expected_count = int(extract_single_value(step))

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert data['total_count'] == expected_count
    assert len(data['tickets']) == expected_count


@then('section tickets should be returned with count:')
def section_tickets_returned_with_count(step, context):
    """Verify section tickets are returned with correct count."""
    expected_count = int(extract_single_value(step))

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert data['total_count'] == expected_count
    assert len(data['tickets']) == expected_count


@then('available tickets should be returned with count:')
def available_tickets_returned_with_count(step, context):
    """Verify available tickets are returned with correct count."""
    expected_count = int(extract_single_value(step))

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert data['total_count'] == expected_count
    assert len(data['tickets']) == expected_count

    # Verify all returned tickets are available
    for ticket in data['tickets']:
        assert ticket['status'] == 'available'


@then('tickets should include detailed information:')
def verify_ticket_details(step, context):
    """Verify that returned tickets include detailed information."""
    data = extract_table_data(step)

    response = context['response']
    assert response.status_code == 200

    response_data = response.json()
    tickets = response_data['tickets']

    # Check that we have tickets
    assert len(tickets) > 0, 'No tickets returned'

    # Map table columns to expected ticket fields
    field_mapping = {'seat_numbers': 'seat_identifier', 'prices': 'price', 'sections': 'section'}

    # Verify each ticket has the expected fields
    for ticket in tickets:
        for column, field in field_mapping.items():
            if data.get(column) == 'true':
                assert field in ticket, f"Expected field '{field}' not found in ticket response"
                assert ticket[field] is not None, f"Field '{field}' should not be None"


@then('reservation status should be:')
def reservation_status_should_be(step, context, execute_sql_statement):
    """Verify reservation status in response or database."""
    data_dict = extract_table_data(step)
    expected_status = data_dict['status']

    # If this is checking API response status
    if expected_status == 'ok':
        response = context['response']
        data = response.json()
        assert data['status'] == expected_status
        return

    # For expiration scenario, check if tickets changed status
    if expected_status == 'expired':
        # After expiration, tickets should be available again
        result = execute_sql_statement(
            "SELECT COUNT(*) as count FROM ticket WHERE status = 'available' AND reserved_at IS NULL",
            {},
            fetch=True,
        )
        # At least some tickets should be available now
        assert result[0]['count'] > 0


@then('tickets should return to available:')
def tickets_return_to_available(step, execute_sql_statement):
    """Verify tickets returned to available status."""
    data_dict = extract_table_data(step)
    expected_status = data_dict['status']
    expected_count = int(data_dict['count'])

    # Check that tickets are now available
    result = execute_sql_statement(
        'SELECT COUNT(*) as count FROM ticket WHERE status = :status AND reserved_at IS NULL',
        {'status': expected_status},
        fetch=True,
    )
    actual_count = result[0]['count']
    assert actual_count >= expected_count  # At least this many should be available


# Availability step definitions


@then('the availability response should contain:')
def verify_availability_response(step, context):
    """Verify availability response contains expected statistics."""
    expected_data = extract_table_data(step)

    response = context['response']
    assert response.status_code == 200

    data = response.json()

    # Verify main statistics
    assert data['total_tickets'] == int(expected_data['total_tickets'])
    assert data['available_tickets'] == int(expected_data['available_tickets'])
    assert data['reserved_tickets'] == int(expected_data['reserved_tickets'])
    assert data['sold_tickets'] == int(expected_data['sold_tickets'])


@then('sections availability should include:')
def verify_sections_availability(step, context):
    """Verify sections availability data in response."""
    response = context['response']
    assert response.status_code == 200

    data = response.json()
    sections = data.get('sections', [])

    # Parse expected data from step table
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected = dict(zip(headers, values, strict=True))

        # Find matching section
        section_found = False
        for section in sections:
            if section['section'] == expected['section']:
                section_found = True

                # Verify section totals
                assert section['total_tickets'] == int(expected['subsections']) * int(
                    expected['total_per_subsection']
                )
                assert section['available_tickets'] == int(expected['subsections']) * int(
                    expected['available_per_subsection']
                )

                # Verify subsections count
                assert len(section['subsections']) == int(expected['subsections'])

                # Verify each subsection
                for subsection in section['subsections']:
                    assert subsection['total_tickets'] == int(expected['total_per_subsection'])
                    assert subsection['available_tickets'] == int(
                        expected['available_per_subsection']
                    )
                    assert subsection['reserved_tickets'] == 0
                    assert subsection['sold_tickets'] == 0

                break

        assert section_found, f'Section {expected["section"]} not found in response'


@then('the section availability should contain:')
def verify_section_availability_response(step, context):
    """Verify section-specific availability response."""
    expected_data = extract_table_data(step)

    response = context['response']
    assert response.status_code == 200

    data = response.json()

    # Verify section data
    assert data['section'] == expected_data['section']
    assert data['total_tickets'] == int(expected_data['total_tickets'])
    assert data['available_tickets'] == int(expected_data['available_tickets'])
    assert data['reserved_tickets'] == int(expected_data['reserved_tickets'])
    assert data['sold_tickets'] == int(expected_data['sold_tickets'])


@then('subsections availability should include:')
def verify_subsections_availability(step, context):
    """Verify subsections availability data in response."""
    response = context['response']
    assert response.status_code == 200

    data = response.json()
    subsections = data.get('subsections', [])

    # Parse expected data from step table
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected = dict(zip(headers, values, strict=True))

        # Find matching subsection
        subsection_found = False
        for subsection in subsections:
            if subsection['subsection'] == int(expected['subsection']):
                subsection_found = True

                assert subsection['total_tickets'] == int(expected['total_tickets'])
                assert subsection['available_tickets'] == int(expected['available_tickets'])
                assert subsection['reserved_tickets'] == int(expected['reserved_tickets'])
                assert subsection['sold_tickets'] == int(expected['sold_tickets'])

                break

        assert subsection_found, f'Subsection {expected["subsection"]} not found in response'


@then('sections availability should be empty')
def verify_sections_availability_empty(context):
    """Verify sections availability is empty."""
    response = context['response']
    assert response.status_code == 200

    data = response.json()
    sections = data.get('sections', [])
    assert len(sections) == 0, f'Expected empty sections, got {len(sections)} sections'


@then('subsection availability should include:')
def verify_subsection_availability(step, context):
    """Verify detailed subsection availability data."""
    response = context['response']
    assert response.status_code == 200

    data = response.json()
    sections = data.get('sections', [])

    # Create a lookup table for expected subsections
    expected_subsections = {}
    rows = step.data_table.rows[1:]  # Skip header
    for row in rows:
        section = row.cells[0].value
        subsection = int(row.cells[1].value)
        key = f'{section}_{subsection}'
        expected_subsections[key] = {
            'total_tickets': int(row.cells[2].value),
            'available_tickets': int(row.cells[3].value),
            'reserved_tickets': int(row.cells[4].value),
            'sold_tickets': int(row.cells[5].value),
        }

    # Verify each expected subsection
    found_subsections = {}
    for section_data in sections:
        section_name = section_data['section']
        for subsection_data in section_data.get('subsections', []):
            subsection_num = subsection_data['subsection']
            key = f'{section_name}_{subsection_num}'
            found_subsections[key] = subsection_data

    for key, expected in expected_subsections.items():
        assert key in found_subsections, f'Subsection {key} not found in response'
        actual = found_subsections[key]

        assert actual['total_tickets'] == expected['total_tickets'], (
            f'Subsection {key} total_tickets: expected {expected["total_tickets"]}, got {actual["total_tickets"]}'
        )
        assert actual['available_tickets'] == expected['available_tickets'], (
            f'Subsection {key} available_tickets: expected {expected["available_tickets"]}, got {actual["available_tickets"]}'
        )
        assert actual['reserved_tickets'] == expected['reserved_tickets'], (
            f'Subsection {key} reserved_tickets: expected {expected["reserved_tickets"]}, got {actual["reserved_tickets"]}'
        )
        assert actual['sold_tickets'] == expected['sold_tickets'], (
            f'Subsection {key} sold_tickets: expected {expected["sold_tickets"]}, got {actual["sold_tickets"]}'
        )


@then('some subsections should have reservations:')
def verify_subsections_have_reservations(step, context):
    """Verify that subsections have the expected total reservations."""
    expected_data = extract_table_data(step)
    expected_total_reserved = int(expected_data['total_reserved'])

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    sections = data.get('sections', [])

    actual_total_reserved = 0
    for section_data in sections:
        for subsection_data in section_data.get('subsections', []):
            actual_total_reserved += subsection_data.get('reserved_tickets', 0)

    assert actual_total_reserved == expected_total_reserved, (
        f'Total reserved tickets: expected {expected_total_reserved}, got {actual_total_reserved}'
    )


@then('subsection statuses should be mixed:')
def verify_mixed_subsection_statuses(step, context):
    """Verify that subsections have mixed statuses (reserved and sold)."""
    expected_data = extract_table_data(step)
    expected_total_reserved = int(expected_data['total_reserved'])
    expected_total_sold = int(expected_data['total_sold'])

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    sections = data.get('sections', [])

    actual_total_reserved = 0
    actual_total_sold = 0
    for section_data in sections:
        for subsection_data in section_data.get('subsections', []):
            actual_total_reserved += subsection_data.get('reserved_tickets', 0)
            actual_total_sold += subsection_data.get('sold_tickets', 0)

    assert actual_total_reserved == expected_total_reserved, (
        f'Total reserved tickets: expected {expected_total_reserved}, got {actual_total_reserved}'
    )
    assert actual_total_sold == expected_total_sold, (
        f'Total sold tickets: expected {expected_total_sold}, got {actual_total_sold}'
    )
