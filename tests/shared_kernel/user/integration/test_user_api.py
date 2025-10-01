from fastapi.testclient import TestClient

from src.platform.constant.route_constant import USER_CREATE
from tests.util_constant import DEFAULT_PASSWORD, TEST_EMAIL


class TestUserAPI:
    def test_create_user(self, client: TestClient):
        email = TEST_EMAIL
        user_data = {
            'email': email,
            'password': DEFAULT_PASSWORD,
            'name': 'John Doe',
            'role': 'buyer',
        }
        response = client.post(USER_CREATE, json=user_data)
        assert response.status_code == 201
        data = response.json()
        assert data['email'] == email
        assert data['role'] == 'buyer'
        assert data['name'] == 'John Doe'
        assert 'id' in data
        assert 'password' not in data

    def test_create_another_user(self, client: TestClient):
        user_data = {
            'email': TEST_EMAIL,
            'password': DEFAULT_PASSWORD,
            'name': 'Jane Smith',
            'role': 'seller',
        }
        response = client.post(USER_CREATE, json=user_data)
        assert response.status_code == 201
        data = response.json()
        assert data['email'] == TEST_EMAIL
        assert data['role'] == 'seller'
