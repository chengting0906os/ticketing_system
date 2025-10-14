"""Fixtures for seat reservation SSE integration test"""

import multiprocessing
import os
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


def run_server(port: int, env_vars: dict):
    """Run uvicorn server in separate process with environment variables."""
    # Set environment variables in the spawned process
    for key, value in env_vars.items():
        os.environ[key] = value

    from test.test_app import app

    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')


@pytest.fixture(scope='function')
def http_server():
    """Start a real HTTP server for SSE testing with dynamic port."""
    # Get a free port
    port = get_free_port()

    # Capture critical environment variables for the spawned process
    # Include all database and service configuration
    env_vars = {
        'KVROCKS_KEY_PREFIX': os.getenv('KVROCKS_KEY_PREFIX', 'test_'),
        'KVROCKS_HOST': os.getenv('KVROCKS_HOST', 'localhost'),
        'KVROCKS_PORT': os.getenv('KVROCKS_PORT', '6666'),
        'KVROCKS_DB': os.getenv('KVROCKS_DB', '0'),
        'POSTGRES_HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'POSTGRES_PORT': os.getenv('POSTGRES_PORT', '5432'),
        'POSTGRES_USER': os.getenv('POSTGRES_USER', 'postgres'),
        'POSTGRES_PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'POSTGRES_DB': os.getenv('POSTGRES_DB', 'ticketing_system_test_db'),
    }

    # Use spawn instead of fork to avoid issues in multi-threaded environments (CI)
    ctx = multiprocessing.get_context('spawn')
    server_process = ctx.Process(target=run_server, args=(port, env_vars), daemon=True)
    server_process.start()

    # Wait for server to be ready with health check
    base_url = f'http://127.0.0.1:{port}'
    max_retries = 30  # 30 seconds max wait
    for i in range(max_retries):
        try:
            response = httpx.get(f'{base_url}/health', timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            if i == max_retries - 1:
                # Last attempt failed, still yield the URL
                # (tests will fail with clear error if server didn't start)
                break
            time.sleep(1)

    yield base_url

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
