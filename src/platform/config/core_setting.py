import os
from pathlib import Path
from typing import List

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.platform.message_queue.kafka_constant_builder import (
    KafkaProducerTransactionalIdBuilder,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# In AWS environments (production, development, staging), use environment variables only
# In local development (local_dev), use .env file if it exists
_AWS_ENVIRONMENTS = ('production', 'development', 'staging')
_CURRENT_ENV = os.getenv('ENVIRONMENT', 'local_dev')

if _CURRENT_ENV in _AWS_ENVIRONMENTS:
    # AWS: Don't load from file, rely on ECS task definition env vars
    _ENV_FILE = None
else:
    # Local: Use .env if exists, otherwise None (pydantic will skip)
    _ENV_PATH = _PROJECT_ROOT / '.env'
    _ENV_FILE = str(_ENV_PATH) if _ENV_PATH.exists() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,  # None in AWS, .env path in local
        env_ignore_empty=True,
        extra='ignore',
    )

    PROJECT_NAME: str = 'Ticketing System'
    VERSION: str = '0.1.0'
    DEBUG: bool = False  # Set to False in evention

    # Database (Optional - only required for services that use PostgreSQL)
    POSTGRES_SERVER: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: SecretStr | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_PORT: int | None = None

    # Read Replica (Optional - for read-write separation)
    POSTGRES_REPLICA_SERVER: str | None = None
    POSTGRES_REPLICA_PORT: int | None = None

    # Database Connection Pool Configuration (SQLAlchemy)
    # Formula: PostgreSQL max_connections (200) × 0.8 = 160 total
    # Distributed across 8 workers (4 ticketing + 4 reservation)
    # Per worker: 160 / 8 = 20 connections
    DB_POOL_SIZE_WRITE: int = 1  # Write pool per worker
    DB_POOL_SIZE_READ: int = 1  # Read pool per worker
    DB_POOL_MAX_OVERFLOW: int = 10  # Max overflow per worker (total: 20 per worker)
    DB_POOL_TIMEOUT: int = 5  # Fail fast: 5 seconds
    DB_POOL_RECYCLE: int = 3600  # Recycle connections after 1 hour
    DB_POOL_PRE_PING: bool = True  # Verify connection health before use

    # Database Connection Pool Configuration (asyncpg - for bulk operations)
    ASYNCPG_POOL_MIN_SIZE: int = 2  # Minimum connections in pool (per container)
    ASYNCPG_POOL_MAX_SIZE: int = 15  # Maximum connections in pool (per container)
    ASYNCPG_POOL_COMMAND_TIMEOUT: int = 60  # Command timeout in seconds
    ASYNCPG_POOL_MAX_INACTIVE_LIFETIME: float = 300.0  # Max idle time (5 min)
    ASYNCPG_POOL_TIMEOUT: float = 2.0  # Connection acquire timeout (2s - fail fast)
    ASYNCPG_POOL_MAX_QUERIES: int = 50000  # Max queries per connection

    @property
    def DATABASE_URL_ASYNC(self) -> str | None:
        if not all(
            [
                self.POSTGRES_SERVER,
                self.POSTGRES_USER,
                self.POSTGRES_PASSWORD,
                self.POSTGRES_DB,
                self.POSTGRES_PORT,
            ]
        ):
            return None
        password = self.POSTGRES_PASSWORD.get_secret_value()  # type: ignore
        return f'postgresql+asyncpg://{self.POSTGRES_USER}:{password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'

    @property
    def DATABASE_READ_URL_ASYNC(self) -> str | None:
        if not all(
            [
                self.POSTGRES_SERVER,
                self.POSTGRES_USER,
                self.POSTGRES_PASSWORD,
                self.POSTGRES_DB,
                self.POSTGRES_PORT,
            ]
        ):
            return None
        password = self.POSTGRES_PASSWORD.get_secret_value()  # type: ignore
        if self.POSTGRES_REPLICA_SERVER and self.POSTGRES_REPLICA_PORT:
            return f'postgresql+asyncpg://{self.POSTGRES_USER}:{password}@{self.POSTGRES_REPLICA_SERVER}:{self.POSTGRES_REPLICA_PORT}/{self.POSTGRES_DB}'
        # Fall back to primary if replica not configured
        return self.DATABASE_URL_ASYNC

    @property
    def DATABASE_URL_SYNC(self) -> str | None:
        if not all(
            [
                self.POSTGRES_SERVER,
                self.POSTGRES_USER,
                self.POSTGRES_PASSWORD,
                self.POSTGRES_DB,
                self.POSTGRES_PORT,
            ]
        ):
            return None
        password = self.POSTGRES_PASSWORD.get_secret_value()  # type: ignore
        return f'postgresql://{self.POSTGRES_USER}:{password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'

    # Security
    SECRET_KEY: SecretStr
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    ALGORITHM: str

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = []  # add your frontend URL here

    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str) and not v.startswith('['):
            return [i.strip() for i in v.split(',')]
        elif isinstance(v, list):
            return v
        return []

    # FastAPI Users
    RESET_PASSWORD_TOKEN_SECRET: SecretStr
    VERIFICATION_TOKEN_SECRET: SecretStr

    # Kvrocks Configuration (Redis protocol + Kvrocks storage)
    KVROCKS_HOST: str = 'localhost'
    KVROCKS_PORT: int = 6666
    KVROCKS_DB: int = 0
    KVROCKS_PASSWORD: str = ''
    REDIS_DECODE_RESPONSES: bool = True  # Kvrocks also uses Redis protocol

    # Kvrocks Connection Pool Configuration
    KVROCKS_POOL_MAX_CONNECTIONS: int = 10000  # Max connections in pool
    KVROCKS_POOL_SOCKET_TIMEOUT: int = (
        30  # Socket read/write timeout (seconds) - AWS VPC can be slower
    )
    KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT: int = (
        30  # Connection timeout (seconds) - Allow time for DNS
    )
    KVROCKS_POOL_SOCKET_KEEPALIVE: bool = True  # Enable TCP keepalive
    KVROCKS_POOL_HEALTH_CHECK_INTERVAL: int = 30  # Health check interval (seconds)

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = 'localhost:9092'
    KAFKA_PRODUCER_RETRIES: int = 3
    KAFKA_CONSUMER_AUTO_OFFSET_RESET: str = 'latest'
    KAFKA_TOTAL_PARTITIONS: int = 100  # Total partitions per topic for even distribution
    KAFKA_REPLICATION_FACTOR: int = 3  # Topic replication factor for high availability
    KAFKA_TOPIC_RETENTION_MS: int = 604800000  # Topic retention: 7 days (in milliseconds)
    SUBSECTIONS_PER_SECTION: int = (
        10  # Number of subsections per section (for partition calculation)
    )

    @property
    def KAFKA_TOPIC_CONFIG(self) -> dict[str, str]:
        return {'retention.ms': str(self.KAFKA_TOPIC_RETENTION_MS)}

    @property
    def KAFKA_PRODUCER_INSTANCE_ID(self) -> str:
        return f'{os.uname().nodename}-{os.getpid()}'

    @property
    def KAFKA_CONSUMER_INSTANCE_ID(self) -> str:
        return f'{os.uname().nodename}-{os.getpid()}'


settings = Settings()


# Kafka Config Helper
class KafkaConfig:
    """Kafka configuration for Exactly-Once processing"""

    def __init__(self, *, event_id: int, service: str) -> None:
        """
        Args:
            event_id: Event ID
            service: Service name ('ticketing', 'booking', or 'reservation')

        Note: instance_id is obtained from settings at runtime to avoid fork issues
        """

        self.event_id = event_id
        self.service = service
        self._transactional_id_builder = KafkaProducerTransactionalIdBuilder

    @property
    def instance_id(self) -> str:
        return settings.KAFKA_PRODUCER_INSTANCE_ID

    @property
    def transactional_id(self) -> str:
        if self.service == 'ticketing':
            return self._transactional_id_builder.ticketing_service(
                event_id=self.event_id, instance_id=self.instance_id
            )
        elif self.service == 'booking':
            return self._transactional_id_builder.booking_service(
                event_id=self.event_id, instance_id=self.instance_id
            )
        elif self.service == 'reservation':
            return self._transactional_id_builder.reservation_service(
                event_id=self.event_id, instance_id=self.instance_id
            )
        else:
            raise ValueError(f'Unknown service: {self.service}')

    @property
    def producer_config(self) -> dict:
        return {
            'transactional.id': self.transactional_id,
            'retries': settings.KAFKA_PRODUCER_RETRIES,
            # Connection retry settings - handle broker not ready during startup
            'reconnect.backoff.ms': 1000,  # Initial reconnect backoff (1s)
            'reconnect.backoff.max.ms': 30000,  # Max reconnect backoff (30s)
            'socket.connection.setup.timeout.ms': 60000,  # Connection timeout (60s)
        }

    @property
    def consumer_config(self) -> dict:
        return {
            'auto.offset.reset': settings.KAFKA_CONSUMER_AUTO_OFFSET_RESET,
            # Connection retry settings - handle broker not ready during startup
            'reconnect.backoff.ms': 1000,  # Initial reconnect backoff (1s)
            'reconnect.backoff.max.ms': 30000,  # Max reconnect backoff (30s)
            'socket.connection.setup.timeout.ms': 60000,  # Connection timeout (60s)
            # Consumer group settings
            'session.timeout.ms': 45000,  # Session timeout (45s)
            'heartbeat.interval.ms': 15000,  # Heartbeat interval (15s)
            # Fetch latency optimization
            'fetch.wait.max.ms': 50,  # Reduce from default 500ms to 50ms
        }
