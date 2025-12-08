"""
Conftest for pure unit tests - no external dependencies.

Override session-scoped fixtures to avoid database/Kvrocks connections.
"""

import pytest
from collections.abc import Generator
from unittest.mock import MagicMock


@pytest.fixture(scope='session')
def client() -> Generator[MagicMock, None, None]:
    """Mock client for unit tests - no FastAPI app needed"""
    yield MagicMock()


@pytest.fixture(scope='session')
def seller_user() -> dict:
    """Mock seller user for unit tests"""
    return {'id': 1, 'email': 'seller@test.com', 'name': 'Test Seller', 'role': 'seller'}


@pytest.fixture(scope='session')
def buyer_user() -> dict:
    """Mock buyer user for unit tests"""
    return {'id': 2, 'email': 'buyer@test.com', 'name': 'Test Buyer', 'role': 'buyer'}


@pytest.fixture(scope='session')
def another_buyer_user() -> dict:
    """Mock another buyer user for unit tests"""
    return {'id': 3, 'email': 'buyer2@test.com', 'name': 'Another Buyer', 'role': 'buyer'}
