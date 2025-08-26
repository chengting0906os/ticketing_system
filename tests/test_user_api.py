"""User API tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_as_organizer(client: AsyncClient):
    """Test registering a user as organizer."""
    user_data = {
        "email": "alice@example.com",
        "password": "Pass123!",
        "first_name": "Alice",
        "last_name": "Chen",
        "role": "organizer",
    }
    
    response = await client.post("/api/users", json=user_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Chen"
    assert data["role"] == "organizer"


@pytest.mark.asyncio
async def test_register_as_customer(client: AsyncClient):
    """Test registering a user as customer."""
    user_data = {
        "email": "bob@example.com",
        "password": "Pass456!",
        "first_name": "Bob",
        "last_name": "Smith",
        "role": "customer",
    }
    
    response = await client.post("/api/users", json=user_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "bob@example.com"
    assert data["first_name"] == "Bob"
    assert data["last_name"] == "Smith"
    assert data["role"] == "customer"


@pytest.mark.asyncio
async def test_duplicate_email_registration_fails(client: AsyncClient):
    """Test that duplicate email registration fails."""
    # First, create a user
    user_data = {
        "email": "alice@example.com",
        "password": "Pass123!",
        "first_name": "Test",
        "last_name": "User",
        "role": "customer",
    }
    
    response = await client.post("/api/users", json=user_data)
    assert response.status_code == 201
    
    # Try to register with the same email
    duplicate_user_data = {
        "email": "alice@example.com",
        "password": "Pass456!",
        "first_name": "Alice",
        "last_name": "Wang",
        "role": "customer",
    }
    
    response = await client.post("/api/users", json=duplicate_user_data)
    assert response.status_code == 400
    assert "REGISTER_USER_ALREADY_EXISTS" in response.text