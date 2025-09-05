from fastapi.testclient import TestClient


class TestUserAPI:
    def test_create_user(self, client: TestClient):
        """Test creating a new user."""
        # Arrange - 現在可以使用固定的 email，因為每次測試都會清理資料庫
        email = 'test@example.com'
        user_data = {
            'email': email,
            'password': 'Test123456!',
            'name': 'John Doe',
            'role': 'buyer',
        }

        # Act
        response = client.post('/api/users', json=user_data)

        # Assert
        if response.status_code != 201:
            print(f'Error: {response.json()}')
        assert response.status_code == 201
        data = response.json()
        assert data['email'] == email
        assert data['role'] == 'buyer'
        assert data['name'] == 'John Doe'
        assert 'id' in data
        assert 'password' not in data  # Password should not be returned

    def test_create_another_user(self, client: TestClient):
        """Test creating another user - should work because DB is cleaned."""
        # Arrange - 可以用相同的 email 因為資料庫已清理
        user_data = {
            'email': 'test@example.com',
            'password': 'Test123456!',
            'name': 'Jane Smith',
            'role': 'seller',
        }

        # Act
        response = client.post('/api/users', json=user_data)

        # Assert
        if response.status_code != 201:
            print(f'Error response: {response.json()}')
        assert response.status_code == 201
        data = response.json()
        assert data['email'] == 'test@example.com'
        assert data['role'] == 'seller'
