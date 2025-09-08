from fastapi.testclient import TestClient
from pytest_bdd import given


@given('a buyer user exists')
def create_buyer_user(step, client: TestClient):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    user_data = dict(zip(headers, values, strict=True))
    response = client.post('/api/users', json=user_data)
    assert response.status_code == 201, f'Failed to create buyer user: {response.text}'
