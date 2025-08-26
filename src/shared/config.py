"""Application configuration."""

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_ignore_empty=True,
        extra='ignore',
    )
    
    PROJECT_NAME: str = 'Ticketing System'
    VERSION: str = '0.1.0'
    
    # Database
    POSTGRES_SERVER: str = 'localhost'
    POSTGRES_USER: str = 'py_arch_lab'
    POSTGRES_PASSWORD: str = 'py_arch_lab'
    POSTGRES_DB: str = 'ticketing_db'
    POSTGRES_PORT: int = 5432
    
    @property
    def DATABASE_URL(self) -> str:
        """Get database URL."""
        return f'postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'
    
    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Get sync database URL for Alembic."""
        return f'postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'
    
    # Security
    SECRET_KEY: str = 'your-secret-key-here-change-in-production'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = 'HS256'
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = []  # 如果需要前端訪問，加入前端網址
    
    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        """Assemble CORS origins."""
        if isinstance(v, str) and not v.startswith('['):
            return [i.strip() for i in v.split(',')]
        elif isinstance(v, list):
            return v
        return []
    
    # FastAPI Users
    RESET_PASSWORD_TOKEN_SECRET: str = 'reset-password-secret-change-in-production'
    VERIFICATION_TOKEN_SECRET: str = 'verification-secret-change-in-production'


settings = Settings()
