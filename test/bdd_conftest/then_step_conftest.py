"""Common BDD Step Definitions for pytest-bdd.

This file contains reusable "Then" step definitions that can be shared across all BDD tests.
Import this file in bdd_steps_loader.py to use the common steps.

Usage in bdd_steps_loader.py:
    from test.bdd_conftest.then_step_conftest import *  # noqa: F401, F403

Available Then steps:
    - the response status code should be {status_code}
    - the error message should contain "{text}"
    - the response should contain "{field}"
    - the response field "{field}" should be "{value}"
    - the response should be empty
    - the database "{table}" should have {count} rows where "{column}" is "{value}"
    - the database "{table}" row should match:
"""

from collections.abc import Callable
from typing import Any

import httpx
from pytest_bdd import parsers, then
from pytest_bdd.model import Step


# ============ Then Steps - Response Status ============


@then(parsers.parse('the response status code should be {status_code:d}'))
def then_response_status_code(
    status_code: int,
    context: dict[str, Any],
) -> None:
    """Verify response status code.

    Example:
        Then the response status code should be 200
        Then the response status code should be 201
        Then the response status code should be 400
    """
    response: httpx.Response = context['response']
    assert response.status_code == status_code, (
        f'Expected {status_code}, got {response.status_code}: {response.text}'
    )


@then(parsers.parse('the error message should contain "{text}"'))
def then_error_message_contains(
    text: str,
    context: dict[str, Any],
) -> None:
    """Verify error message contains expected text (case-insensitive).

    Example:
        Then the error message should contain "not found"
        Then the error message should contain "Invalid"
    """
    response: httpx.Response = context['response']
    error_data = response.json()
    error_message = str(error_data.get('detail', ''))
    assert text.lower() in error_message.lower(), (
        f'Expected "{text}" in error message, got: {error_message}'
    )


# ============ Then Steps - Response Body ============


@then(parsers.parse('the response should contain "{field}"'))
def then_response_contains_field(
    field: str,
    context: dict[str, Any],
) -> None:
    """Verify response contains specified field.

    Example:
        Then the response should contain "id"
        Then the response should contain "status"
    """
    response_data = context.get('response_data')
    assert response_data is not None, 'Response data is empty'
    assert field in response_data, f'Response does not contain field "{field}": {response_data}'


@then(parsers.parse('the response field "{field}" should be "{value}"'))
def then_response_field_equals(
    field: str,
    value: str,
    context: dict[str, Any],
) -> None:
    """Verify response field has expected value.

    Example:
        Then the response field "status" should be "pending"
        Then the response field "role" should be "buyer"
    """
    response_data = context.get('response_data')
    assert response_data is not None, 'Response data is empty'
    assert field in response_data, f'Response does not contain field "{field}": {response_data}'

    actual_value = response_data[field]
    # Handle type conversion for comparison
    if isinstance(actual_value, bool):
        expected = value.lower() == 'true'
    elif isinstance(actual_value, int):
        expected = int(value)
    else:
        expected = value

    assert actual_value == expected, f'Expected {field}="{expected}", got "{actual_value}"'


@then('the response should be empty')
def then_response_empty(
    context: dict[str, Any],
) -> None:
    """Verify response is empty or null.

    Example:
        Then the response should be empty
    """
    response_data = context.get('response_data')
    assert response_data is None or response_data == {}, (
        f'Expected empty response, got: {response_data}'
    )


@then(parsers.parse('the response should have {count:d} items'))
def then_response_has_count(
    count: int,
    context: dict[str, Any],
) -> None:
    """Verify response list has expected count.

    Example:
        Then the response should have 5 items
    """
    response_data = context.get('response_data')
    assert response_data is not None, 'Response data is empty'
    assert isinstance(response_data, list), f'Expected list response, got: {type(response_data)}'
    assert len(response_data) == count, f'Expected {count} items, got {len(response_data)}'


# ============ Then Steps - Response Data (Unified) ============


def _match_value(*, actual: Any, expected: str) -> bool:
    """Match actual value against expected string pattern.

    Supports special patterns:
        - not_null: value is not None
        - null: value is None
        - {any_int}: value is any integer
        - PAY_MOCK_*: value starts with PAY_MOCK_
        - Regular values: exact match (with type conversion)
    """
    if expected == 'not_null':
        return actual is not None
    if expected == 'null':
        return actual is None
    if expected == '{any_int}':
        return isinstance(actual, int)
    if expected.endswith('*'):
        prefix = expected[:-1]
        return isinstance(actual, str) and actual.startswith(prefix)
    # Type conversion for comparison
    if isinstance(actual, bool):
        return actual == (expected.lower() == 'true')
    if isinstance(actual, int):
        try:
            return actual == int(expected)
        except ValueError:
            return False
    return str(actual) == expected


@then('the response data should include:')
def then_response_data_should_include(
    step: Step,
    context: dict[str, Any],
) -> None:
    """Verify response data includes specified field-value pairs.

    Format: headers on top row, values on second row (can extend horizontally)

    Example:
        Then the response data should include:
          | status     | id       |
          | processing | not_null |

        And the response data should include:
          | name         | venue_name   | is_active |
          | Rock Concert | Taipei Arena | true      |
    """
    response_data = context.get('response_data')
    assert response_data is not None, 'Response data is empty'

    # Parse datatable: row[0] = headers, row[1] = values
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]

    for field, expected in zip(headers, values, strict=True):
        assert field in response_data, f'Response does not contain field "{field}": {response_data}'
        actual = response_data[field]
        assert _match_value(actual=actual, expected=expected), (
            f'Field "{field}": expected "{expected}", got "{actual}"'
        )


# ============ Then Steps - Database Verification ============


@then(
    parsers.parse('the database "{table}" should have {count:d} rows where "{column}" is "{value}"')
)
def then_database_count(
    table: str,
    count: int,
    column: str,
    value: str,
    execute_sql_statement: Callable[..., list[dict[str, Any]]],
) -> None:
    """Verify database table has expected row count with condition.

    Example:
        Then the database "ticket" should have 10 rows where "status" is "available"
        Then the database "booking" should have 0 rows where "status" is "cancelled"
    """
    result = execute_sql_statement(
        f'SELECT COUNT(*) as count FROM "{table}" WHERE {column} = :value',  # noqa: S608
        {'value': value},
        fetch=True,
    )
    actual_count = result[0]['count'] if result else 0
    assert actual_count == count, (
        f'Expected {count} rows in "{table}" where {column}="{value}", got {actual_count}'
    )


@then('the database row should match:')
def then_database_row_should_match(
    step: Step,
    execute_sql_statement: Callable[..., list[dict[str, Any]]],
) -> None:
    """Verify database row matches expected values.

    Format: headers on top row, values on second row
    Must include 'table' and at least one condition column.

    Example:
        Then the database row should match:
          | table  | status    | count |
          | ticket | available | 100   |
    """
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    data = dict(zip(headers, values, strict=True))

    table = data.pop('table')
    conditions = []
    params = {}

    for i, (col, val) in enumerate(data.items()):
        if val == 'not_null':
            conditions.append(f'{col} IS NOT NULL')
        elif val == 'null':
            conditions.append(f'{col} IS NULL')
        else:
            conditions.append(f'{col} = :param_{i}')
            params[f'param_{i}'] = val

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    query = f'SELECT COUNT(*) as count FROM "{table}" WHERE {where_clause}'  # noqa: S608

    result = execute_sql_statement(query, params, fetch=True)
    actual_count = result[0]['count'] if result else 0
    assert actual_count > 0, f'No rows found in "{table}" matching conditions: {data}'
