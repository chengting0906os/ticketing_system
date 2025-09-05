"""Shared exceptions for the application."""


class DomainException(Exception):
    """Base domain exception with status code and message."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)
