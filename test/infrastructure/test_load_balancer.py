"""
Infrastructure Integration Tests for Nginx Load Balancer

Test Category: Infrastructure Testing
Purpose: Verify nginx routing and load balancing configuration

Run with: make test-infra
"""

import httpx
import pytest


@pytest.fixture(scope='module')
def nginx_client():
    """HTTP client for nginx load balancer.

    When running inside Docker, use the container name.
    When running locally, use localhost.
    """
    # Docker Compose creates a hostname from the service name
    # Tests run inside ticketing-service container, so we use nginx service name
    return httpx.Client(base_url='http://nginx', timeout=10.0)


# ==============================================================================
# Infrastructure Tests - Only 2 Essential Tests
# ==============================================================================


@pytest.mark.infra
def test_nginx_health_endpoint(nginx_client):
    """
    Infrastructure: Verify nginx is running and responding.

    This tests:
    - Nginx container is up
    - Health check endpoint works
    - Basic HTTP routing
    """
    response = nginx_client.get('/health')

    assert response.status_code == 200, 'Nginx should respond to health check'

    data = response.json()
    assert data['status'] == 'healthy', 'Health status should be healthy'
    assert data['service'] == 'nginx-alb', 'Should identify as nginx load balancer'


@pytest.mark.infra
def test_nginx_routes_to_backend_services(nginx_client):
    """
    Infrastructure: Verify nginx routes requests to backend services.

    This tests:
    - Path-based routing configuration
    - Backend services are accessible through nginx
    - No 502/503/504 gateway errors
    """
    # Test routes that should work (may return 404 if endpoint doesn't exist, but should route)
    test_paths = [
        '/api/user',
        '/api/event',
        '/api/booking',
        '/api/reservation',
    ]

    for path in test_paths:
        response = nginx_client.get(path)

        # Should successfully route (not get bad gateway errors)
        # Actual status depends on backend (might be 200, 404, etc.)
        # But should NOT be 502 (Bad Gateway), 503 (Service Unavailable), 504 (Gateway Timeout)
        assert response.status_code not in [502, 503, 504], (
            f'Path {path} should route to backend service (got {response.status_code})'
        )


if __name__ == '__main__':
    # Allow running directly for quick testing
    pytest.main([__file__, '-v', '--tb=short'])
