"""Test steps for datatable."""

from messages import Step
from pytest_bdd import given


def get_datatable_row_values(row):
    """Extract values from a DataTable row."""
    return list(map(lambda cell: cell.value, row.cells))


@given('I check step datatable')
def check_datatable(step: Step):
    """Check how datatable works."""
    if step.data_table is None:
        raise ValueError("No data table provided in step")
    
    title_row, *data_rows = step.data_table.rows
    assert get_datatable_row_values(title_row) == ["first", "second"]
    assert get_datatable_row_values(data_rows[0]) == ["a", "b"]
