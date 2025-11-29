"""
Service context extraction for distributed logging.

Provides service identification across cloud and local environments
for better log traceability in distributed systems.
"""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_service_context() -> str:
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
