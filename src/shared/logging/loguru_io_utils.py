from inspect import FullArgSpec, getfile, getfullargspec, getsourcelines
from os.path import basename
from re import sub
from time import time
from typing import Any, Callable, Optional

from src.shared.logging.loguru_io_config import (
    DEPTH_LINE,
    SENSITIVE_KEYWORDS,
    GeneratorMethod,
    call_depth_var,
    chain_start_time_var,
)


def handle_yield(yield_method: Optional[GeneratorMethod] = None) -> str:
    return f'yield: {yield_method} | ' if yield_method else ''


def get_chain_start_time() -> float:
    if not (start_time := chain_start_time_var.get()):
        start_time = time()
        chain_start_time_var.set(start_time)
    return start_time


def fetch_layer_depth() -> str:
    return DEPTH_LINE * (call_depth_var.get() - 1)


def build_call_target_func_path(func: Callable[..., Any]) -> str:
    lineno = getsourcelines(func)[1]
    return f'{basename(getfile(getattr(func, "__func__", func)))}::{func.__qualname__}:{lineno}'


def reset_call_depth():
    layer = call_depth_var.get() - 1
    call_depth_var.set(layer)
    if not layer:
        chain_start_time_var.set(0)


def normalize_args_kwargs(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> tuple[tuple[Any, ...], dict[Any, Any]]:
    if hasattr(func, '__wrapped__'):
        func = func.__wrapped__  # type: ignore
    full_arg_spec: FullArgSpec = getfullargspec(func)
    spec_args: list[str] = full_arg_spec.args

    if not full_arg_spec.varkw:
        kw_list: list[str] = spec_args + full_arg_spec.kwonlyargs
        kwargs = {k: v for k, v in kwargs.items() if k in kw_list}

    if not full_arg_spec.varargs:
        spec_default: list[Any] = list(full_arg_spec.defaults) if full_arg_spec.defaults else []
        args_dict = dict(
            zip(
                spec_args,
                [None] * (len(spec_args) - len(spec_default)) + spec_default,
                strict=False,
            )
        )
        if args_dict := {k: v for k, v in args_dict.items() if k not in kwargs}:
            args_max_len: int = len(args_dict)
            args_min_len: int = len([value for value in args_dict.values() if value is None])
            if len(args) not in range(args_min_len, args_max_len + 1):
                args = args[:args_max_len]
        else:
            args = ()

    return args, kwargs


def mask_sensitive(data_str: Any) -> Any:
    try:
        data_str_ = str(data_str)
        new_data_str = sub(  # type: ignore
            r"\1\2='********'\3",
            data_str_,
        )
        return data_str if data_str_ == new_data_str else new_data_str
    except Exception:
        return data_str


def should_mask_keyword(keyword: Any, value: Any) -> Any:
    return '********' if keyword in SENSITIVE_KEYWORDS else value
