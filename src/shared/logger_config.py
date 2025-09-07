"""Centralized logging configuration."""

import sys

from loguru import logger as loguru_logger

from src.shared.path import LOG_DIR


# Constants for extra fields
FIRST_TIME = 'first_time'
LAYER = 'layer'
UP_DOWN = 'up_down'
DESTINATION = 'destination'


# Log format configuration
log_format = ' | '.join(
    (
        '<lk>{time:YYYY-MM-DD HH:mm:ss.SSS}</>',
        '<lvl>{level:<8}</>',
        f'<lg>{{extra[{LAYER}]}}{{extra[{UP_DOWN}]}}</> '
        f'<c>{{file}}::{{function}}:{{line}}</>=><y>{{extra[{DESTINATION}]}}</>',
        '{message}',
        '<lk>{elapsed}</>',
        f'<lk>{{extra[{FIRST_TIME}]:<18}}</>',
    )
)

# Configure logger
loguru_logger.remove()  # Remove default handler to avoid duplicate output and use custom format
custom_logger = loguru_logger.bind(
    **{FIRST_TIME: '', LAYER: '', DESTINATION: '', UP_DOWN: ''}
)

# Add console output
custom_logger.add(sys.stdout, format=log_format)

# Add file output with daily rotation and compression
custom_logger.add(
    f'{LOG_DIR}/{{time:YYYY-MM-DD_HH}}.log',
    format=log_format,
    rotation='1 day',
    retention='30 days',
    compression='zip',
    enqueue=True,
)
