from pathlib import Path
from typing import List

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _PROJECT_ROOT / '.env'
_ENV_FILE = _ENV_PATH if _ENV_PATH.exists() else (_PROJECT_ROOT / '.env.example')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_ignore_empty=True,
        extra='ignore',
    )

    PROJECT_NAME: str = 'Ticketing System'
    VERSION: str = '0.1.0'
    DEBUG: bool = True  # Set to False in evention

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_PORT: int

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        password = self.POSTGRES_PASSWORD.get_secret_value()
        return f'postgresql+asyncpg://{self.POSTGRES_USER}:{password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'

    @property
    def DATABASE_URL_SYNC(self) -> str:
        password = self.POSTGRES_PASSWORD.get_secret_value()
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
    REDIS_DECODE_RESPONSES: bool = True  # Kvrocks 也用 Redis 協議

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = 'localhost:9092'
    KAFKA_SECURITY_PROTOCOL: str = 'PLAINTEXT'
    KAFKA_GROUP_ID: str = 'ticketing-system'
    KAFKA_AUTO_OFFSET_RESET: str = 'earliest'
    KAFKA_ENABLE_IDEMPOTENCE: bool = True
    KAFKA_ACKS: str = 'all'
    KAFKA_RETRIES: int = 3
    KAFKA_MAX_IN_FLIGHT_REQUESTS: int = 1
    KAFKA_COMPRESSION_TYPE: str = 'gzip'
    KAFKA_BATCH_SIZE: int = 16384
    KAFKA_LINGER_MS: int = 10

    @property
    def KAFKA_PRODUCER_CONFIG(self) -> dict:
        return {
            'bootstrap_servers': self.KAFKA_BOOTSTRAP_SERVERS.split(','),
            'security_protocol': self.KAFKA_SECURITY_PROTOCOL,
            'enable_idempotence': self.KAFKA_ENABLE_IDEMPOTENCE,
            'acks': self.KAFKA_ACKS,
            'retries': self.KAFKA_RETRIES,
            'max_in_flight_requests_per_connection': self.KAFKA_MAX_IN_FLIGHT_REQUESTS,
            'compression_type': self.KAFKA_COMPRESSION_TYPE,
            'batch_size': self.KAFKA_BATCH_SIZE,
            'linger_ms': self.KAFKA_LINGER_MS,
        }

    @property
    def KAFKA_CONSUMER_CONFIG(self) -> dict:
        return {
            'bootstrap_servers': self.KAFKA_BOOTSTRAP_SERVERS.split(','),
            'security_protocol': self.KAFKA_SECURITY_PROTOCOL,
            'group_id': self.KAFKA_GROUP_ID,
            'auto_offset_reset': self.KAFKA_AUTO_OFFSET_RESET,
            'enable_auto_commit': False,
            'max_poll_records': 500,
        }


settings = Settings()  # type: ignore
