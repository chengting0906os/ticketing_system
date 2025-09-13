"""Then steps for ticket BDD tests."""

from pytest_bdd import then

from tests.shared.utils import extract_table_data


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
