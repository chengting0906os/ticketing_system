"""
Pytest configuration for CDK tests

Fixtures and test setup for infrastructure tests
"""

import pytest


@pytest.fixture(scope='session')
def aws_account():
    """Test AWS account ID"""
    return '123456789012'


@pytest.fixture(scope='session')
def aws_region():
    """Test AWS region"""
    return 'us-east-1'


def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        'markers', 'slow: marks tests as slow (deselect with "-m \'not slow\'")'
    )
    config.addinivalue_line(
        'markers', 'integration: marks tests as integration tests (require AWS)'
    )
