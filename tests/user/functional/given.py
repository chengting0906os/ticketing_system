from fastapi.testclient import TestClient
from pytest_bdd import given
from tests.shared.utils import extract_table_data


@given('a buyer user exists')
def create_buyer_user(step, client: TestClient):
    user_data = extract_table_data(step)
    response = client.post('/api/user', json=user_data)
    assert response.status_code == 201, f'Failed to create buyer user: {response.text}'
