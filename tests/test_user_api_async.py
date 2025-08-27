"""API tests with proper async isolation using httpx."""

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.main import app
from src.shared.database import Base, get_async_session


# Test database URL
DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/ticketing_db"


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create async engine for tests."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine):
    """Create async session with transaction rollback."""
    async_session_maker = async_sessionmaker(
        async_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def async_client(async_session):
    """Create async test client."""
    async def override_get_async_session():
        yield async_session
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_buyer_user(async_client):
    """Test creating a buyer user."""
    response = await async_client.post(
        "/api/users",
        json={
            "email": "buyer@example.com",
            "password": "Test123456!",
            "first_name": "John",
            "last_name": "Buyer",
            "role": "buyer"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "buyer@example.com"
    assert data["first_name"] == "John"
    assert data["last_name"] == "Buyer"
    assert data["role"] == "buyer"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_seller_user(async_client):
    """Test creating a seller user."""
    response = await async_client.post(
        "/api/users",
        json={
            "email": "seller@example.com",
            "password": "Test123456!",
            "first_name": "Alice",
            "last_name": "Seller",
            "role": "seller"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "seller@example.com"
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Seller"
    assert data["role"] == "seller"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_user_duplicate_email(async_client):
    """Test creating user with duplicate email."""
    # Create first user
    response1 = await async_client.post(
        "/api/users",
        json={
            "email": "duplicate@example.com",
            "password": "Test123456!",
            "first_name": "First",
            "last_name": "User",
            "role": "buyer"
        }
    )
    assert response1.status_code == 201
    
    # Try to create second user with same email
    response2 = await async_client.post(
        "/api/users",
        json={
            "email": "duplicate@example.com",
            "password": "Test123456!",
            "first_name": "Second",
            "last_name": "User",
            "role": "seller"
        }
    )
    assert response2.status_code == 400
    assert response2.json()["detail"] == "REGISTER_USER_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_create_user_invalid_password(async_client):
    """Test creating user with invalid password."""
    response = await async_client.post(
        "/api/users",
        json={
            "email": "test@example.com",
            "password": "short",  # Too short
            "first_name": "Test",
            "last_name": "User",
            "role": "buyer"
        }
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_user_invalid_email(async_client):
    """Test creating user with invalid email."""
    response = await async_client.post(
        "/api/users",
        json={
            "email": "not-an-email",
            "password": "Test123456!",
            "first_name": "Test",
            "last_name": "User",
            "role": "buyer"
        }
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_user_default_role(async_client):
    """Test creating user without specifying role (should default to buyer)."""
    response = await async_client.post(
        "/api/users",
        json={
            "email": "default@example.com",
            "password": "Test123456!",
            "first_name": "Default",
            "last_name": "Role"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "buyer"  # Should default to buyer


@pytest.mark.asyncio
async def test_database_isolation(async_client):
    """Test that each test has isolated database state."""
    # This should succeed because previous tests are isolated
    response = await async_client.post(
        "/api/users",
        json={
            "email": "buyer@example.com",
            "password": "Test123456!",
            "first_name": "Isolated",
            "last_name": "Test",
            "role": "buyer"
        }
    )
    assert response.status_code == 201
