from fastapi.testclient import TestClient


class TestUserAPI:
    def test_create_user(self, client: TestClient):
        email = 'test@example.com'
        user_data = {'email': email, 'password': 'P@ssw0rd', 'name': 'John Doe', 'role': 'buyer'}
        response = client.post('/api/users', json=user_data)
        assert response.status_code == 201
        data = response.json()
        assert data['email'] == email
        assert data['role'] == 'buyer'
        assert data['name'] == 'John Doe'
        assert 'id' in data
        assert 'password' not in data

    def test_create_another_user(self, client: TestClient):
        user_data = {
            'email': 'test@example.com',
            'password': 'P@ssw0rd',
            'name': 'Jane Smith',
            'role': 'seller',
        }
        response = client.post('/api/users', json=user_data)
        assert response.status_code == 201
        data = response.json()
        assert data['email'] == 'test@example.com'
        assert data['role'] == 'seller'
