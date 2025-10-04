"""Fixtures for seat reservation SSE integration tests"""

import multiprocessing
import socket
import time

import httpx
import pytest
import uvicorn


def get_free_port():
    """Get a free port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def run_server(port: int):
    """Run uvicorn server in separate process."""
    from src.main import app

    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')


@pytest.fixture(scope='function')
def http_server():
    """Start a real HTTP server for SSE testing with dynamic port."""
    # Get a free port
    port = get_free_port()

    # Use spawn instead of fork to avoid issues in multi-threaded environments (CI)
    ctx = multiprocessing.get_context('spawn')
    server_process = ctx.Process(target=run_server, args=(port,), daemon=True)
    server_process.start()

    # Wait for server to be ready
    time.sleep(3)  # Increased wait time for CI environment

    yield f'http://127.0.0.1:{port}'

    # Cleanup
    server_process.terminate()
    server_process.join(timeout=5)


@pytest.fixture
async def async_client(http_server):
    """Async HTTP client for SSE testing."""
    async with httpx.AsyncClient(base_url=http_server, timeout=10.0) as client:
        yield client


@pytest.fixture
def context():
    """Shared context for BDD scenarios."""
    return {}
