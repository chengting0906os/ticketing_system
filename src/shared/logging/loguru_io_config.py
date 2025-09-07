"""Centralized logging configuration."""

import sys

from loguru import logger as loguru_logger

from src.shared.path import LOG_DIR


# Constants for extra fields
CHAIN_START_TIME = 'chain_start_time'
LAYER_MARKER = 'layer_marker'
ENTRY_MARKER = 'entry_marker'
EXIT_MARKER = 'exit_marker'
CALL_TARGET = 'call_target'


# Log format configuration
log_format = ' | '.join(
    (
        '<lk>{time:YYYY-MM-DD HH:mm:ss.SSS}</>',
        '<lvl>{level:<8}</>',
        f'<lg>{{extra[{LAYER_MARKER}]}}{{extra[{ENTRY_MARKER}]}}{{extra[{EXIT_MARKER}]}}</> '
        f'<c>{{file}}::{{function}}:{{line}}</>=><y>{{extra[{CALL_TARGET}]}}</>',
        '{message}',
        '<lk>{elapsed}</>',
        f'<lk>{{extra[{CHAIN_START_TIME}]:<18}}</>',
    )
)

# Configure logger
loguru_logger.remove()  # Remove default handler to avoid duplicate output and use custom format
custom_logger = loguru_logger.bind(
    **{CHAIN_START_TIME: '', LAYER_MARKER: '', ENTRY_MARKER: '', EXIT_MARKER: '', CALL_TARGET: ''}
)

# Add console output with custom format
custom_logger.add(sys.stdout, format=log_format)

# Add file output with daily rotation and compression
custom_logger.add(
    f'{LOG_DIR}/{{time:YYYY-MM-DD_HH}}.log',
    format=log_format,
    rotation='1 day',
    retention='14 days',
    compression='gz',
    enqueue=True,
)


custom_logger = custom_logger
