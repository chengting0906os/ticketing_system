from functools import wraps
from inspect import (
    iscoroutinefunction,
    isgeneratorfunction,
)
import types
from typing import Any, Callable, Optional, TypeVar, cast

from src.shared.logging.generator_wrapper import GeneratorWrapper
from src.shared.logging.loguru_io_constants import (
    ExtraField,
    GeneratorMethod,
    call_depth_var,
)
from src.shared.logging.loguru_io_utils import (
    build_function_path,
    fetch_first_time,
    fetch_layer,
    handle_yield,
    mask_sensitive,
    normalize_args_kwargs,
    reset_call_depth,
    should_mask_keyword,
)


T = TypeVar('T', bound=Callable[..., Any])


class LoguruIO:
    depth = 2

    def log_args_kwargs(self, *args, yield_method: Optional[GeneratorMethod] = None, **kwargs):
        call_depth_var.set(call_depth_var.get() + 1)
        self.extra |= {
            ExtraField.FIRST_TIME: fetch_first_time(),
            ExtraField.LAYER: fetch_layer(),
            ExtraField.UP_DOWN: '┌',
        }
        self._logger.bind(**self.extra).opt(depth=self.depth).debug(
            f'{handle_yield(yield_method)}args: {self.mask_sensitive(args)}, kwargs: {self.mask_sensitive(kwargs)}'
        )
        self.extra[ExtraField.UP_DOWN] = '└'

    def log_return(self, return_value, yield_method: Optional[GeneratorMethod] = None):
        self._logger.bind(**self.extra).opt(depth=self.depth).debug(
            f'{handle_yield(yield_method)}return: {self.mask_sensitive(return_value)}'
        )

    def log_error(self, e, yield_method: Optional[GeneratorMethod] = None):
        if not hasattr(e, '_logged'):
            self._logger.bind(**self.extra).opt(depth=self.depth).error(
                f'{handle_yield(yield_method)}Error: {self.mask_sensitive(e)}'
            )
            e._logged = True
        if self.reraise:
            raise e

    def _hide_from_traceback(self, func):
        func.__code__ = func.__code__.replace(co_filename=cast(types.FunctionType, self._logger.catch).__code__.co_filename)
        return func

    def mask_sensitive(self, data: Any) -> Any:
        if isinstance(data, dict):
            new_data = {}
            for key, value in data.items():
                new_data[key] = self.mask_sensitive(should_mask_keyword(key, value))
            return new_data
        elif isinstance(data, list | tuple):
            return type(data)(self.mask_sensitive(item) for item in data)
        return mask_sensitive(data)

    def __init__(self, logger_, reraise: bool = True):
        self._logger = logger_
        self.reraise = reraise
        self.extra = {}

    def __call__(self, func):
        self.extra[ExtraField.DESTINATION] = build_function_path(func)
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    self.log_args_kwargs(*args, **kwargs)
                    args, kwargs = normalize_args_kwargs(func, *args, **kwargs)
                    return_value = await func(*args, **kwargs)
                    self.log_return(return_value)
                    return return_value
                except Exception as e:
                    self.log_error(e)
                finally:
                    reset_call_depth()
            return self._hide_from_traceback(async_wrapper)
            
        elif isgeneratorfunction(func):

            @wraps(func)
            def generator_wrapper(*args, **kwargs):
                try:
                    self.log_args_kwargs(*args, **kwargs)
                    gen = func(*args, **kwargs)
                    self.log_return(gen)
                    return GeneratorWrapper(gen, self)
                except Exception as e:
                    self.log_error(e)
                finally:
                    reset_call_depth()
            return self._hide_from_traceback(generator_wrapper)
            
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    self.log_args_kwargs(*args, **kwargs)
                    args, kwargs = normalize_args_kwargs(func, *args, **kwargs)
                    return_value = func(*args, **kwargs)
                    self.log_return(return_value)
                    return return_value
                except Exception as e:
                    self.log_error(e)
                finally:
                    reset_call_depth()
            return self._hide_from_traceback(sync_wrapper)
