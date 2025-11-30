from collections.abc import Awaitable, Generator
from functools import wraps
from inspect import (
    iscoroutinefunction,
    isgeneratorfunction,
)
import types
from typing import TYPE_CHECKING, Any, Callable, Optional, ParamSpec, TypeVar, cast, overload


if TYPE_CHECKING:
    from loguru import Logger as LoguruLogger

from src.platform.config.core_setting import settings
from src.platform.exception.exceptions import CustomBaseError
from src.platform.logging.generator_wrapper import GeneratorWrapper
from src.platform.logging.loguru_io_config import (
    ExtraField,
    GeneratorMethod,
    call_depth_var,
    custom_logger,
)
from src.platform.logging.loguru_io_utils import (
    build_call_target_func_path,
    get_chain_start_time,
    handle_yield,
    mask_sensitive,
    normalize_args_kwargs,
    reset_call_depth,
    should_mask_keyword,
    truncate_content,
)

# TypeVar for preserving function type through decorator
_F = TypeVar('_F', bound=Callable[..., Any])


class LoguruIO:
    def __init__(
        self, custom_logger: 'LoguruLogger', *, reraise: bool = True, truncate_content: bool = False
    ) -> None:
        self._custom_logger = custom_logger
        self.reraise = reraise
        self.truncate_content = truncate_content
        self.extra: dict[str, Any] = {}
        self.depth = 2  # Adjusted for wrapper functions

    def log_args_kwargs_content(
        self, *args: Any, yield_method: Optional[GeneratorMethod] = None, **kwargs: Any
    ) -> None:
        call_depth_var.set(call_depth_var.get() + 1)
        self.extra |= {
            ExtraField.CHAIN_START_TIME: get_chain_start_time(),
        }
        if settings.DEBUG:  # Skip expensive mask_sensitive when not logging
            self._custom_logger.bind(**self.extra).opt(depth=self.depth).debug(
                f'{handle_yield(yield_method)}args: {self.mask_sensitive(args)}, kwargs: {self.mask_sensitive(kwargs)}'
            )

    def log_return_content(
        self, return_value: Any, yield_method: Optional[GeneratorMethod] = None
    ) -> None:
        if settings.DEBUG:  # Skip expensive mask_sensitive when not logging
            self._custom_logger.bind(**self.extra).opt(depth=self.depth).debug(
                f'{handle_yield(yield_method)}return: {self.mask_sensitive(return_value)}'
            )

    def _hide_from_traceback(self, func: Callable[..., Any]) -> Callable[..., Any]:
        func.__code__ = func.__code__.replace(  # type: ignore[attr-defined]
            co_filename=cast(types.FunctionType, self._custom_logger.catch).__code__.co_filename
        )
        return func

    def mask_sensitive(self, data: Any) -> Any:
        if isinstance(data, dict):
            new_data = {}
            for key, value in data.items():
                new_data[key] = self.mask_sensitive(should_mask_keyword(key, value))
            processed_data = new_data
        elif isinstance(data, list | tuple):
            processed_data = type(data)(self.mask_sensitive(item) for item in data)
        else:
            processed_data = mask_sensitive(data)

        # Apply truncation if enabled
        if self.truncate_content:
            return truncate_content(processed_data)
        return processed_data

    def __call__(self, func: _F) -> _F:
        self.extra[ExtraField.CALL_TARGET] = build_call_target_func_path(func)
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    self.log_args_kwargs_content(
                        *args, **kwargs
                    )  # pyrefly: ignore[bad-argument-type]
                    args, kwargs = normalize_args_kwargs(func, *args, **kwargs)
                    return_value = await cast(Awaitable[Any], func(*args, **kwargs))
                    self.log_return_content(return_value)
                    return return_value
                except Exception as e:
                    # Skip if already logged (avoid duplicate logs when exception bubbles up)
                    if not getattr(e, '_has_logged', False):
                        e._has_logged = True
                        if isinstance(e, CustomBaseError):
                            self._custom_logger.bind(**self.extra).opt(depth=self.depth).error(
                                f'{type(e).__name__}: {e}'
                            )
                        else:
                            self._custom_logger.bind(**self.extra).opt(depth=self.depth).exception(
                                f'{type(e).__name__}: {e}'
                            )
                    if self.reraise:
                        raise
                    return None
                finally:
                    reset_call_depth()

            return cast(_F, self._hide_from_traceback(async_wrapper))

        elif isgeneratorfunction(func):

            @wraps(func)
            def generator_wrapper(*args: Any, **kwargs: Any) -> GeneratorWrapper | None:
                try:
                    self.log_args_kwargs_content(
                        *args, **kwargs
                    )  # pyrefly: ignore[bad-argument-type]
                    gen_obj = cast(Generator[Any, Any, Any], func(*args, **kwargs))
                    self.log_return_content(gen_obj)
                    return GeneratorWrapper(gen_obj, self)
                except Exception as e:
                    if not getattr(e, '_has_logged', False):
                        e._has_logged = True
                        if isinstance(e, CustomBaseError):
                            self._custom_logger.bind(**self.extra).opt(depth=self.depth).error(
                                f'{type(e).__name__}: {e}'
                            )
                        else:
                            self._custom_logger.bind(**self.extra).opt(depth=self.depth).exception(
                                f'{type(e).__name__}: {e}'
                            )
                    if self.reraise:
                        raise
                    return None
                finally:
                    reset_call_depth()

            return cast(_F, self._hide_from_traceback(generator_wrapper))

        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    self.log_args_kwargs_content(
                        *args, **kwargs
                    )  # pyrefly: ignore[bad-argument-type]
                    args, kwargs = normalize_args_kwargs(func, *args, **kwargs)
                    return_value = func(*args, **kwargs)
                    self.log_return_content(return_value)
                    return return_value
                except Exception as e:
                    if not getattr(e, '_has_logged', False):
                        e._has_logged = True
                        if isinstance(e, CustomBaseError):
                            self._custom_logger.bind(**self.extra).opt(depth=self.depth).error(
                                f'{type(e).__name__}: {e}'
                            )
                        else:
                            self._custom_logger.bind(**self.extra).opt(depth=self.depth).exception(
                                f'{type(e).__name__}: {e}'
                            )
                    if self.reraise:
                        raise
                    return None
                finally:
                    reset_call_depth()

            return cast(_F, self._hide_from_traceback(sync_wrapper))


_P = ParamSpec('_P')
_T = TypeVar('_T')


class Logger:
    base = custom_logger

    @overload
    @staticmethod
    def io(func: Callable[_P, _T]) -> Callable[_P, _T]: ...

    @overload
    @staticmethod
    def io(func: None = ..., *, reraise: bool = ..., truncate_content: bool = ...) -> LoguruIO: ...

    @staticmethod
    def io(
        func: Callable[_P, _T] | None = None, *, reraise: bool = True, truncate_content: bool = True
    ) -> Callable[_P, _T] | LoguruIO:
        if func:
            return LoguruIO(
                custom_logger=custom_logger, reraise=reraise, truncate_content=truncate_content
            )(func)
        return LoguruIO(
            custom_logger=custom_logger, reraise=reraise, truncate_content=truncate_content
        )
