from contextvars import ContextVar
from datetime import datetime
from enum import StrEnum
import logging
import os
import sys
from typing import TYPE_CHECKING
import zoneinfo

from loguru import logger as loguru_logger


if TYPE_CHECKING:
    from loguru import Logger as LoguruLogger

from src.platform.config.core_setting import settings
from src.platform.constant.path import LOG_DIR
from src.platform.logging.service_context import get_service_context


# Use test log directory if in test environment
LOG_DIR = os.environ.get('TEST_LOG_DIR', LOG_DIR)


# Constants and shared variables for LoguruIO
SENSITIVE_KEYWORDS = {
    'password',
}

chain_start_time_var: ContextVar[float] = ContextVar('first_time_var', default=0)
call_depth_var: ContextVar[int] = ContextVar('call_depth_var', default=0)


class ExtraField(StrEnum):
    SERVICE_CONTEXT = 'service_context'
    CHAIN_START_TIME = 'chain_start_time'
    CALL_TARGET = 'call_target'


class GeneratorMethod(StrEnum):
    NEXT = 'next'
    SEND = 'send'
    THROW = 'throw'


def _parse_http_status_level(message: str) -> str | None:
    """
    Parse HTTP status code from granian access logs and return appropriate log level.

    Format: '127.0.0.1 - "GET /api/user/me HTTP/1.1" - 200 - 8ms'

    Returns:
        Log level string if HTTP status found, None otherwise
    """
    if ' - "' not in message or ' HTTP/' not in message:
        return None

    try:
        # Split by quotes to get status code section
        parts = message.split('"')
        if len(parts) < 3:
            return None

        # Parse status code from ' - 200 - 8ms'
        status_parts = parts[2].strip().split()
        if len(status_parts) < 2 or status_parts[0] != '-':
            return None

        status_code = int(status_parts[1])

        # Map status code to log level
        if status_code >= 500:
            return 'CRITICAL'
        if status_code >= 400:
            return 'ERROR'
        if status_code >= 300:
            return 'WARNING'
        if status_code >= 200:
            return 'SUCCESS'
        return 'INFO'

    except (ValueError, IndexError):
        return None


_intercept_bound_logger = None  # Cached bound logger for InterceptHandler


def _get_intercept_bound_logger() -> 'LoguruLogger':
    """Get or create bound logger with default extra fields (cached)."""
    global _intercept_bound_logger
    if _intercept_bound_logger is None:
        _intercept_bound_logger = loguru_logger.bind(
            **{
                ExtraField.SERVICE_CONTEXT: get_service_context(),
                ExtraField.CHAIN_START_TIME: '',
                ExtraField.CALL_TARGET: '',
            }
        )
    return _intercept_bound_logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()

        # Filter out formatting debug logs
        if record.levelno <= logging.DEBUG:
            # Block format template debug messages (gherkin pattern matching)
            if 'format ' in message and ' -> ' in message:
                return  # Ignore gherkin formatting messages
            # Block asyncio selector debug messages
            if 'Using selector:' in message and 'Selector' in message:
                return  # Ignore asyncio selector messages

        # Also block logs from Kafka loggers regardless of level
        if record.name.startswith('kafka') and record.levelno <= logging.DEBUG:
            return

        # Parse HTTP status code from granian access logs
        level = _parse_http_status_level(message)
        if level is None:
            # Get corresponding Loguru level if it exists
            try:
                level = loguru_logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore
            depth += 1

        # Use cached bound logger
        _get_intercept_bound_logger().opt(depth=depth, exception=record.exc_info).log(
            level, message
        )


# Log format for LoguruIO decorated functions
io_log_format = ' | '.join(
    (
        f'<c>{{extra[{ExtraField.SERVICE_CONTEXT}]}}</>',
        '<lvl>{level:<8}</>',
        f'<c>{{file}}::{{function}}:{{line}}</>=><y>{{extra[{ExtraField.CALL_TARGET}]}}</>',
        '{message}',
        '<lk>{elapsed}</>',
        f'<lk>{{extra[{ExtraField.CHAIN_START_TIME}]:<18}}</>',
    )
)


# Configure logger
loguru_logger.remove()  # Remove default handler to avoid duplicate output and use custom format
custom_logger = loguru_logger.bind(
    **{
        ExtraField.SERVICE_CONTEXT: get_service_context(),
        ExtraField.CHAIN_START_TIME: '',
        ExtraField.CALL_TARGET: '',
    }
)

# Determine minimum log level based on DEBUG setting
min_log_level = 'DEBUG' if settings.DEBUG else 'INFO'

# Add console output with custom format
custom_logger.add(sys.stdout, format=io_log_format, level=min_log_level, enqueue=True)

# Add file output only in DEBUG mode or when explicitly enabled
# Production uses stdout only (collected by CloudWatch/Loki)
if settings.DEBUG:
    taipei_tz = zoneinfo.ZoneInfo('Asia/Taipei')
    now_taipei = datetime.now(taipei_tz)
    log_filename = (
        f'test_{now_taipei.strftime("%Y-%m-%d_%H")}.log'
        if os.environ.get('TEST_LOG_DIR')
        else f'{now_taipei.strftime("%Y-%m-%d_%H")}.log'
    )
    custom_logger.add(
        f'{LOG_DIR}/{log_filename}',
        format=io_log_format,
        rotation='1 hour',
        retention='7 days',
        compression='gz',
        enqueue=True,
        level=min_log_level,
    )

# Intercept standard logging → loguru
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
