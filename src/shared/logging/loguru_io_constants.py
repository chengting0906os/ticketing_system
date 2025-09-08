"""Constants and shared variables for LoguruIO."""

from contextvars import ContextVar
from enum import StrEnum


SENSITIVE_KEYWORDS = {
    'password',
}

# Visual markers for logging
ENTRY_ARROW = '┌'
DEPTH_LINE = '│'
EXIT_ARROW = '└'

chain_start_time_var: ContextVar[float] = ContextVar('first_time_var', default=0)
call_depth_var: ContextVar[int] = ContextVar('call_depth_var', default=0)


class ExtraField(StrEnum):
    CHAIN_START_TIME = 'chain_start_time'
    LAYER_MARKER = 'layer_marker'
    ENTRY_MARKER = 'entry_marker'
    EXIT_MARKER = 'exit_marker'
    CALL_TARGET = 'call_target'


class GeneratorMethod(StrEnum):
    NEXT = 'next'
    SEND = 'send'
    THROW = 'throw'
