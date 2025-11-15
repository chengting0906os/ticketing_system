from contextvars import ContextVar
from datetime import datetime
from enum import StrEnum
import logging
import os
import sys
import zoneinfo

from loguru import logger as loguru_logger

from src.platform.constant.path import LOG_DIR
from src.platform.config.core_setting import settings

# Use test log directory if in test environment
LOG_DIR = os.environ.get('TEST_LOG_DIR', LOG_DIR)


# Constants and shared variables for LoguruIO
SENSITIVE_KEYWORDS = {
    'password',
}

# Visual markers for logging
DEPTH_LINE = '│'
ENTRY_ARROW = '┌'
EXIT_ARROW = '└'

chain_start_time_var: ContextVar[float] = ContextVar('first_time_var', default=0)
call_depth_var: ContextVar[int] = ContextVar('call_depth_var', default=0)


class ExtraField(StrEnum):
    SERVICE_CONTEXT = 'service_context'
    CHAIN_START_TIME = 'chain_start_time'
    LAYER_MARKER = 'layer_marker'
    ENTRY_MARKER = 'entry_marker'
    EXIT_MARKER = 'exit_marker'
    CALL_TARGET = 'call_target'


class GeneratorMethod(StrEnum):
    NEXT = 'next'
    SEND = 'send'
    THROW = 'throw'


def get_service_context() -> str:
    """
    Extract service context for logging: service_name@env:task_id

    Examples:
        - Cloud: 'api-service@production:f630d9ab'
        - Local: 'unknown@local_dev:12345'

    Returns:
        Formatted service context string
    """
    service_name = os.getenv('SERVICE_NAME', 'unknown')
    deploy_env = os.getenv('DEPLOY_ENV', 'local_dev')

    # Extract ECS Task ID from metadata URI
    task_id = 'local'
    metadata_uri = os.getenv('ECS_CONTAINER_METADATA_URI_V4', '')
    if metadata_uri:
        # Extract task ID from URI like: http://169.254.170.2/v4/{task_id}-{timestamp}
        try:
            task_id_with_ts = metadata_uri.split('/')[-1]
            task_id = task_id_with_ts.split('-')[0][:8]  # First 8 chars for brevity
        except (IndexError, ValueError):
            task_id = 'ecs'
    else:
        # Use PID for local development
        task_id = str(os.getpid())

    return f'{service_name}@{deploy_env}:{task_id}'


class InterceptHandler(logging.Handler):
    def emit(self, record):
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
        if record.name.startswith(('kafka', 'aiokafka')):
            if record.levelno <= logging.DEBUG:  # Block DEBUG, INFO for Kafka loggers
                return

        # Parse HTTP status code from granian access logs
        # Format: '127.0.0.1 - "GET /api/user/me HTTP/1.1" - 200 - 8ms'
        # Also supports HTTP/2.0, HTTP/3.0, etc.
        if (
            ' - "' in message and ' HTTP/' in message
        ):  # Format: '127.0.0.1 - "GET /api/user/me HTTP/2.0" - 200 - 8ms'
            # Extract status code from the format
            try:
                parts = message.split('"')
                if len(parts) >= 3:
                    # parts[2] should be like ' - 200 - 8ms'
                    status_parts = parts[2].strip().split()
                    if len(status_parts) >= 2 and status_parts[0] == '-':
                        status_code = int(status_parts[1])

                        # Adjust log level based on status code
                        if status_code >= 500:
                            level = 'CRITICAL'
                        elif status_code >= 400:
                            level = 'ERROR'
                        elif status_code >= 300:
                            level = 'WARNING'
                        elif status_code >= 200:
                            level = 'SUCCESS'
                        else:
                            level = 'INFO'
                    else:
                        level = 'INFO'
                else:
                    level = 'INFO'
            except (ValueError, IndexError):
                level = 'INFO'
        else:
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

        # Bind empty extra fields to avoid KeyError
        logger_with_extra = loguru_logger.bind(
            **{
                ExtraField.SERVICE_CONTEXT: get_service_context(),
                ExtraField.CHAIN_START_TIME: '',
                ExtraField.LAYER_MARKER: '',
                ExtraField.ENTRY_MARKER: '',
                ExtraField.EXIT_MARKER: '',
                ExtraField.CALL_TARGET: '',
            }
        )

        logger_with_extra.opt(depth=depth, exception=record.exc_info).log(level, message)


# Log format for LoguruIO decorated functions
io_log_format = ' | '.join(
    (
        f'<c>{{extra[{ExtraField.SERVICE_CONTEXT}]}}</>',
        '<lvl>{level:<8}</>',
        f'<lg>{{extra[{ExtraField.LAYER_MARKER}]}}{{extra[{ExtraField.ENTRY_MARKER}]}}{{extra[{ExtraField.EXIT_MARKER}]}}</> '
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
        ExtraField.LAYER_MARKER: '',
        ExtraField.ENTRY_MARKER: '',
        ExtraField.EXIT_MARKER: '',
        ExtraField.CALL_TARGET: '',
    }
)

# Determine minimum log level based on DEBUG setting
min_log_level = 'DEBUG' if settings.DEBUG else 'INFO'

# Add console output with custom format
custom_logger.add(sys.stdout, format=io_log_format, level=min_log_level)

# Add file output with daily rotation and compression
# Use test_ prefix if in test environment
# Generate filename with Taipei timezone
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
    rotation='1 hour',  # Rotate every hour to match filename pattern
    retention='14 days',
    compression='gz',
    enqueue=True,
    level=min_log_level,
)

# Intercept standard logging
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

for logger_name in [
    'fastapi',
    'sqlalchemy.engine',
    'sqlalchemy.pool',
]:
    logging_logger = logging.getLogger(logger_name)
    logging_logger.handlers = [InterceptHandler()]
    logging_logger.propagate = False

# Aggressively suppress Kafka loggers to prevent debug spam
kafka_loggers = [
    'kafka',
    'kafka.client',
    'kafka.consumer',
    'kafka.producer',
    'kafka.coordinator',
    'kafka.coordinator.assignor',
    'kafka.coordinator.consumer',
    'kafka.consumer.fetcher',
    'kafka.consumer.coordinator',
    'kafka.conn',
]

for logger_name in kafka_loggers:
    kafka_logger = logging.getLogger(logger_name)
    kafka_logger.setLevel(logging.INFO)
    kafka_logger.disabled = False
    kafka_logger.propagate = False

custom_logger = custom_logger
