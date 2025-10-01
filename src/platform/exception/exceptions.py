class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ForbiddenError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, 403)


class NotFoundError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, 404)


class ConflictError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class AuthenticationError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, 401)


class LoginError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, 400)
