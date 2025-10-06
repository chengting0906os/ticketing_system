from pytest_bdd import given


@given('I have the number 1')
def have_first_number(calculator_state):
    calculator_state['numbers'].append(1)


@given('I have another number 1')
def have_another_number(calculator_state):
    calculator_state['numbers'].append(1)


@given('I check step datatable')
def check_datatable(step):
    data_table = step.data_table
    rows = data_table.rows
    assert len(rows) == 2
    headers = [cell.value for cell in rows[0].cells]
    assert headers == ['first', 'second']
    data = [cell.value for cell in rows[1].cells]
    assert data == ['a', 'b']
