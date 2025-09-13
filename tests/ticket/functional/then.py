"""Then steps for ticket BDD tests."""

from pytest_bdd import then

from tests.shared.utils import extract_table_data, extract_single_value


@then('tickets are created successfully with:')
def tickets_created_successfully(step, context):
    """Verify tickets were created successfully."""
    data_dict = extract_table_data(step)
    expected_count = int(data_dict['count'])

    response = context['response']
    assert response.status_code == 201

    data = response.json()
    assert data['tickets_created'] == expected_count
    assert 'Successfully created' in data['message']


@then('section tickets have price with:')
def tickets_have_updated_price(step, context):
    """Verify tickets have updated price."""
    data_dict = extract_table_data(step)
    section = data_dict['section']
    expected_price = int(data_dict['price'])

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    for ticket in data['tickets']:
        if ticket['section'] == section:
            assert ticket['price'] == expected_price


@then('section tickets are returned with:')
def correct_ticket_count_returned(step, context):
    """Verify correct number of tickets returned for section."""
    data_dict = extract_table_data(step)
    section = data_dict['section']
    expected_count = int(data_dict['count'])
    expected_status = data_dict['status']

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    section_tickets = [t for t in data['tickets'] if t['section'] == section]
    assert len(section_tickets) == expected_count

    # Also verify status
    for ticket in section_tickets:
        assert ticket['status'] == expected_status


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


@then('only available tickets should be returned with count:')
def only_available_tickets_returned_with_count(step, context):
    """Verify only available tickets are returned with correct count (no sold tickets)."""
    expected_count = int(extract_single_value(step))

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert data['total_count'] == expected_count
    assert len(data['tickets']) == expected_count

    # Verify all returned tickets are available (none should be sold)
    for ticket in data['tickets']:
        assert ticket['status'] == 'available', (
            f'Expected all tickets to be available, but found ticket with status: {ticket["status"]}'
        )


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
