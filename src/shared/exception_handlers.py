"""Centralized exception handlers for FastAPI."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi_users import exceptions as fastapi_users_exceptions

from src.shared.exceptions import DomainError
from src.shared.logging.loguru_io_config import custom_logger


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Handle domain errors."""
    if exc.status_code >= 500:
        custom_logger.exception(f'Domain error: {exc.message}')
    else:
        custom_logger.error(f'Domain error: {exc.message}')
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.message})


async def user_already_exists_handler(
    request: Request, exc: fastapi_users_exceptions.UserAlreadyExists
) -> JSONResponse:
    """Handle user already exists exception from FastAPI Users."""
    custom_logger.error('User already exists')  # 400 error, no stack trace
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={'detail': 'REGISTER_USER_ALREADY_EXISTS'}
    )


async def user_not_exists_handler(
    request: Request, exc: fastapi_users_exceptions.UserNotExists
) -> JSONResponse:
    """Handle user not exists exception from FastAPI Users."""
    custom_logger.error('User not exists')  # 404 error, no stack trace
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': 'USER_NOT_FOUND'})


async def invalid_password_handler(
    request: Request, exc: fastapi_users_exceptions.InvalidPasswordException
) -> JSONResponse:
    """Handle invalid password exception from FastAPI Users."""
    custom_logger.error('Invalid password')  # 400 error, no stack trace
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={'detail': 'INVALID_PASSWORD'}
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError exceptions."""
    custom_logger.error(f'ValueError: {str(exc)}')
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={'detail': str(exc)})


async def general_500_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    custom_logger.exception(f'Unhandled exception: {str(exc)}')
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={'detail': 'Internal server error'},
    )


# Exception handler mapping
EXCEPTION_HANDLERS = {
    DomainError: domain_error_handler,
    fastapi_users_exceptions.UserAlreadyExists: user_already_exists_handler,
    fastapi_users_exceptions.UserNotExists: user_not_exists_handler,
    fastapi_users_exceptions.InvalidPasswordException: invalid_password_handler,
    ValueError: value_error_handler,
    Exception: general_500_exception_handler,  # Catch-all for unhandled exceptions
}


def register_exception_handlers(app):
    for exception_class, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_class, handler)
