"""Shared exceptions for the application."""


class DomainException(Exception):
    """Base domain exception with status code and message."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class BadRequestException(DomainException):
    """Exception for bad request errors (400)."""
    
    def __init__(self, message: str):
        super().__init__(400, message)


class ForbiddenException(DomainException):
    """Exception for forbidden errors (403)."""
    
    def __init__(self, message: str):
        super().__init__(403, message)


class NotFoundException(DomainException):
    """Exception for not found errors (404)."""
    
    def __init__(self, message: str):
        super().__init__(404, message)
