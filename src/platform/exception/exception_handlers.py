from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.platform.exception.exceptions import CustomBaseError


async def custom_error_handler(request: Request, exc: CustomBaseError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.message})


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={'detail': str(exc)})


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={'detail': exc.errors()},
    )


async def general_500_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={'detail': 'Internal server error'},
    )


# Exception handler mapping
EXCEPTION_HANDLERS = {
    CustomBaseError: custom_error_handler,
    ValueError: value_error_handler,
    RequestValidationError: validation_error_handler,
    Exception: general_500_exception_handler,  # Catch-all for unhandled exceptions
}


def register_exception_handlers(app):
    for exception_class, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_class, handler)
