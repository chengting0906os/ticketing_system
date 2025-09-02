"""Given steps for pytest_bdd_ng features."""

from pytest_bdd import given


@given('I have the number 1')
def have_first_number(calculator_state):
    """Store first number."""
    calculator_state['numbers'].append(1)


@given('I have another number 1')
def have_another_number(calculator_state):
    """Store another number."""
    calculator_state['numbers'].append(1)


@given('I check step datatable')
def check_datatable(step):
    """Check that datatable is accessible."""
    # Access the data table
    data_table = step.data_table
    # DataTable has rows attribute (包含標題行和資料行)
    rows = data_table.rows

    # rows[0] 是標題行，rows[1] 是資料行
    assert len(rows) == 2

    # 取得標題
    headers = [cell.value for cell in rows[0].cells]
    assert headers == ['first', 'second']

    # 取得資料
    data = [cell.value for cell in rows[1].cells]
    assert data == ['a', 'b']
