from typing import Any, Callable, Coroutine

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from src.platform.exception.exceptions import CustomBaseError

# Type alias for exception handlers (compatible with Starlette's expected signature)
ExceptionHandler = Callable[[Request, Exception], Coroutine[Any, Any, Response]]


async def custom_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, CustomBaseError) else CustomBaseError(str(exc))
    return JSONResponse(status_code=error.status_code, content={'detail': error.message})


async def value_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={'detail': str(exc)})


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, RequestValidationError) else RequestValidationError([])
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={'detail': error.errors()},
    )


async def general_500_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={'detail': 'Internal server error'},
    )


# Exception handler mapping
EXCEPTION_HANDLERS: dict[type[Exception], ExceptionHandler] = {
    CustomBaseError: custom_error_handler,
    ValueError: value_error_handler,
    RequestValidationError: validation_error_handler,
    Exception: general_500_exception_handler,  # Catch-all for unhandled exceptions
}


def register_exception_handlers(app: FastAPI) -> None:
    for exception_class, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_class, handler)
