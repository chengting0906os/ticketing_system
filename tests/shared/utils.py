from typing import Any, Dict


def extract_table_data(step) -> Dict[str, Any]:
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    return dict(zip(headers, values, strict=True))


def extract_single_value(step, row_index: int = 0, col_index: int = 0) -> str:
    rows = step.data_table.rows
    return rows[row_index].cells[col_index].value
