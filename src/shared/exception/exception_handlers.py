from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    if exc.status_code >= 500:
        Logger.base.exception(f'Domain error: {exc.message}')
    else:
        Logger.base.error(f'Domain error: {exc.message}')
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.message})


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={'detail': str(exc)})


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    Logger.base.error(f'Validation error: {exc.errors()}')
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={'detail': 'LOGIN_BAD_CREDENTIALS'}
    )


async def general_500_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    Logger.base.exception(f'Unhandled exception: {str(exc)}')
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={'detail': 'Internal server error'},
    )


# Exception handler mapping
EXCEPTION_HANDLERS = {
    DomainError: domain_error_handler,
    ValueError: value_error_handler,
    RequestValidationError: validation_error_handler,
    Exception: general_500_exception_handler,  # Catch-all for unhandled exceptions
}


def register_exception_handlers(app):
    for exception_class, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_class, handler)
