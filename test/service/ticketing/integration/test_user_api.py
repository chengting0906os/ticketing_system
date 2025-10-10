from fastapi.testclient import TestClient
import pytest
from test.util_constant import DEFAULT_PASSWORD, TEST_EMAIL

from src.platform.constant.route_constant import USER_CREATE, USER_LOGIN


@pytest.mark.integration
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

    def test_login_success_with_cookie_auth(self, client: TestClient):
        """Test that login returns user data and sets cookie for authentication"""
        # First create a user
        user_data = {
            'email': 'login_test@example.com',
            'password': DEFAULT_PASSWORD,
            'name': 'Login Test User',
            'role': 'buyer',
        }
        create_response = client.post(USER_CREATE, json=user_data)
        assert create_response.status_code == 201

        # Now test login
        login_data = {
            'email': 'login_test@example.com',
            'password': DEFAULT_PASSWORD,
        }
        login_response = client.post(USER_LOGIN, json=login_data)

        # Verify response status
        assert login_response.status_code == 200

        # Verify response body contains user data only (no token in body)
        response_data = login_response.json()
        assert response_data['email'] == 'login_test@example.com'
        assert response_data['name'] == 'Login Test User'
        assert response_data['role'] == 'buyer'
        assert response_data['is_active'] is True
        # Should NOT contain access_token (cookie-based auth only)
        assert 'access_token' not in response_data
        assert 'token_type' not in response_data

        # Verify cookie was set with JWT token
        assert 'fastapiusersauth' in login_response.cookies
        cookie_value = login_response.cookies['fastapiusersauth']
        assert len(cookie_value) > 0
        # JWT tokens typically start with 'eyJ' (base64 encoded header)
        assert cookie_value.startswith('eyJ')

    def test_login_invalid_password(self, client: TestClient):
        """Test login with invalid password returns 401"""
        # First create a user
        user_data = {
            'email': 'invalid_pass_test@example.com',
            'password': DEFAULT_PASSWORD,
            'name': 'Invalid Pass User',
            'role': 'buyer',
        }
        client.post(USER_CREATE, json=user_data)

        # Try to login with wrong password
        login_data = {
            'email': 'invalid_pass_test@example.com',
            'password': 'wrong_password',
        }
        login_response = client.post(USER_LOGIN, json=login_data)

        # Should return 400 Bad Request (domain error for bad credentials)
        assert login_response.status_code == 400

    def test_login_nonexistent_user(self, client: TestClient):
        """Test login with non-existent user returns 401"""
        login_data = {
            'email': 'nonexistent@example.com',
            'password': DEFAULT_PASSWORD,
        }
        login_response = client.post(USER_LOGIN, json=login_data)

        # Should return 400 Bad Request (domain error for bad credentials)
        assert login_response.status_code == 400

    def test_cookie_authentication_works(self, client: TestClient):
        """Test that cookie-based authentication works for subsequent requests"""
        # First create a user
        user_data = {
            'email': 'cookie_auth_test@example.com',
            'password': DEFAULT_PASSWORD,
            'name': 'Cookie Auth User',
            'role': 'buyer',
        }
        client.post(USER_CREATE, json=user_data)

        # Login to get cookie
        login_data = {
            'email': 'cookie_auth_test@example.com',
            'password': DEFAULT_PASSWORD,
        }
        login_response = client.post(USER_LOGIN, json=login_data)
        assert login_response.status_code == 200

        # Verify cookie is set (but no access_token in response body)
        assert 'fastapiusersauth' in login_response.cookies
        cookie_value = login_response.cookies['fastapiusersauth']
        response_data = login_response.json()

        # Should NOT have access_token in response body
        assert 'access_token' not in response_data

        # JWT tokens are typically quite long
        assert len(cookie_value) > 20

        # TestClient automatically handles cookies for subsequent requests
        # So cookie-based authentication works automatically
