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


@then('reservation is created with:')
def reservation_created_successfully(step, context, reservation_state):
    """Verify reservation was created successfully."""
    data_dict = extract_table_data(step)
    expected_buyer_id = int(data_dict['buyer_id'])
    expected_ticket_count = int(data_dict['ticket_count'])
    expected_status = data_dict['status']

    response = context['response']
    assert response.status_code == 200

    data = response.json()
    assert 'reservation_id' in data
    assert data['buyer_id'] == expected_buyer_id
    assert data['ticket_count'] == expected_ticket_count
    assert data['status'] == expected_status

    # Store reservation data for later use
    reservation_state.reservation_id = data['reservation_id']
    reservation_state.buyer_id = data['buyer_id']


@then('reserved tickets status should be:')
def reserved_tickets_status(step, execute_sql_statement):
    """Verify tickets have correct reservation status."""
    data_dict = extract_table_data(step)
    expected_status = data_dict['status']
    expected_count = int(data_dict['count'])

    # Check tickets in database
    result = execute_sql_statement(
        'SELECT COUNT(*) as count FROM ticket WHERE status = :status',
        {'status': expected_status},
        fetch=True,
    )
    actual_count = result[0]['count']
    assert actual_count == expected_count


@then('error message should contain:')
def error_message_contains(step, context):
    """Verify error message contains expected text."""
    expected_message = extract_single_value(step)

    response = context['response']
    data = response.json()

    # Check if it's a validation error or regular error
    if 'detail' in data:
        error_message = str(data['detail'])
    elif 'message' in data:
        error_message = data['message']
    else:
        error_message = str(data)

    assert expected_message in error_message


@then('reservation status should be:')
def reservation_status_should_be(step, execute_sql_statement):
    """Verify reservation status in database."""
    data_dict = extract_table_data(step)
    expected_status = data_dict['status']

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
