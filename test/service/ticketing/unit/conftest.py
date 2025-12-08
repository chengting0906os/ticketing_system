"""
Unit test configuration for ticketing service.

Overrides autouse fixtures from parent conftest to enable pure unit testing
without infrastructure dependencies (Kvrocks, database, etc.).

This module also prevents the session-scoped TestClient from being created.
"""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True, scope='function')
async def clean_kvrocks() -> AsyncGenerator[None, None]:
    """No-op override for unit tests - no real Kvrocks needed"""
    yield


@pytest.fixture(autouse=True, scope='function')
async def clean_database() -> AsyncGenerator[None, None]:
    """No-op override for unit tests - no real database needed"""
    yield


@pytest.fixture(scope='session')
def client() -> Generator[MagicMock, None, None]:
    """Mock client for unit tests - prevents TestClient/lifespan from being created"""
    mock_client = MagicMock(spec=TestClient)
    yield mock_client


@pytest.fixture(autouse=True)
def clear_client_cookies(client: MagicMock) -> Generator[None, None, None]:
    """No-op override for unit tests - uses mock client"""
    yield
