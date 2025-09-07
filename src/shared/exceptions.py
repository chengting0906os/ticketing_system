"""Shared exceptions for the application."""


class DomainError(Exception):
    """Base domain error with customizable message and status code."""
    
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BadRequestException(DomainError):
    """Exception for bad request errors (400)."""
    
    def __init__(self, message: str):
        super().__init__(message, 400)


class ForbiddenException(DomainError):
    """Exception for forbidden errors (403)."""
    
    def __init__(self, message: str):
        super().__init__(message, 403)


class NotFoundException(DomainError):
    """Exception for not found errors (404)."""
    
    def __init__(self, message: str):
        super().__init__(message, 404)
