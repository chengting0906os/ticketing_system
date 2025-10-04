from functools import wraps
from inspect import (
    iscoroutinefunction,
    isgeneratorfunction,
)
import types
from typing import Any, Callable, Optional, TypeVar, cast, overload, ParamSpec

from src.platform.logging.generator_wrapper import GeneratorWrapper
from src.platform.logging.loguru_io_config import (
    ENTRY_ARROW,
    EXIT_ARROW,
    ExtraField,
    GeneratorMethod,
    call_depth_var,
    custom_logger,
)
from src.platform.logging.loguru_io_utils import (
    build_call_target_func_path,
    fetch_layer_depth,
    get_chain_start_time,
    handle_yield,
    mask_sensitive,
    normalize_args_kwargs,
    reset_call_depth,
    should_mask_keyword,
    truncate_content,
)


T = TypeVar('T', bound=Callable[..., Any])


class LoguruIO:
    def __init__(self, custom_logger, reraise: bool = True, truncate_content: bool = False):
        self._custom_logger = custom_logger
        self.reraise = reraise
        self.truncate_content = truncate_content
        self.extra = {}
        self.depth = 2  # Adjusted for wrapper functions

    def log_args_kwargs_content(
        self, *args, yield_method: Optional[GeneratorMethod] = None, **kwargs
    ):
        call_depth_var.set(call_depth_var.get() + 1)
        self.extra |= {
            ExtraField.CHAIN_START_TIME: get_chain_start_time(),
            ExtraField.LAYER_MARKER: fetch_layer_depth(),
            ExtraField.ENTRY_MARKER: ENTRY_ARROW,
            ExtraField.EXIT_MARKER: '',
        }
        self._custom_logger.bind(**self.extra).opt(depth=self.depth).debug(
            f'{handle_yield(yield_method)}args: {self.mask_sensitive(args)}, kwargs: {self.mask_sensitive(kwargs)}'
        )

    def log_return_content(self, return_value, yield_method: Optional[GeneratorMethod] = None):
        self.extra[ExtraField.ENTRY_MARKER] = ''
        self.extra[ExtraField.EXIT_MARKER] = EXIT_ARROW
        self._custom_logger.bind(**self.extra).opt(depth=self.depth).debug(
            f'{handle_yield(yield_method)}return: {self.mask_sensitive(return_value)}'
        )

    def _hide_from_traceback(self, func):
        func.__code__ = func.__code__.replace(
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

    def __call__(self, func):
        self.extra[ExtraField.CALL_TARGET] = build_call_target_func_path(func)
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    self.log_args_kwargs_content(*args, **kwargs)
                    args, kwargs = normalize_args_kwargs(func, *args, **kwargs)
                    return_value = await func(*args, **kwargs)
                    self.log_return_content(return_value)
                    return return_value
                except Exception:
                    raise
                finally:
                    reset_call_depth()

            return self._hide_from_traceback(async_wrapper)

        elif isgeneratorfunction(func):

            @wraps(func)
            def generator_wrapper(*args, **kwargs):
                try:
                    self.log_args_kwargs_content(*args, **kwargs)
                    gen_obj = func(*args, **kwargs)
                    self.log_return_content(gen_obj)
                    return GeneratorWrapper(gen_obj, self)
                except Exception:
                    raise
                finally:
                    reset_call_depth()

            return self._hide_from_traceback(generator_wrapper)

        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    self.log_args_kwargs_content(*args, **kwargs)
                    args, kwargs = normalize_args_kwargs(func, *args, **kwargs)
                    return_value = func(*args, **kwargs)
                    self.log_return_content(return_value)
                    return return_value
                except Exception:
                    raise
                finally:
                    reset_call_depth()

            return self._hide_from_traceback(sync_wrapper)


_P = ParamSpec('_P')
_T = TypeVar('_T')


class Logger:
    base = custom_logger

    @overload
    @staticmethod
    def io(func: Callable[_P, _T]) -> Callable[_P, _T]: ...

    @overload
    @staticmethod
    def io(
        func: None = ..., *, reraise: bool = ..., truncate_content: bool = ...
    ) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]: ...

    @staticmethod
    def io(func=None, *, reraise=True, truncate_content=True):
        if func:
            return LoguruIO(
                custom_logger=custom_logger, reraise=reraise, truncate_content=truncate_content
            )(func)
        return LoguruIO(
            custom_logger=custom_logger, reraise=reraise, truncate_content=truncate_content
        )
