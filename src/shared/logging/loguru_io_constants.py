"""Constants and shared variables for LoguruIO."""

from contextvars import ContextVar
from enum import StrEnum


SENSITIVE_KEYWORDS = {
    'password',
}



first_time_var: ContextVar[float] = ContextVar('first_time_var', default=0)
call_depth_var: ContextVar[int] = ContextVar('call_depth_var', default=0)


class ExtraField(StrEnum):
    FIRST_TIME = 'first_time'  
    LAYER = 'layer'
    UP_DOWN = 'up_down'
    DESTINATION = 'destination'


class GeneratorMethod(StrEnum):
    NEXT = 'next'
    SEND = 'send'
    THROW = 'throw'
