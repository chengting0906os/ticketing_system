class CustomBaseError(Exception):
    """Base class for all custom exceptions - controls logging behavior in @Logger.io"""

    def __init__(self, message: str, status_code: int) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DomainError(CustomBaseError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message, status_code)


class ForbiddenError(CustomBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 403)


class NotFoundError(CustomBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 404)


class ConflictError(CustomBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 409)


class AuthenticationError(CustomBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 401)


class LoginError(CustomBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 400)
