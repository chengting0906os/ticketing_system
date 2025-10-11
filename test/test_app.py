"""
Test application for SSE integration tests.

This module provides a FastAPI application instance configured for SSE testing.
It reuses the main application to ensure consistency between test and production environments.
"""

from src.main import app

__all__ = ['app']
