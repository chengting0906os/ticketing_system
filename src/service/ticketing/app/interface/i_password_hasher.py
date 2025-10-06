from abc import ABC, abstractmethod
from pydantic import SecretStr


class IPasswordHasher(ABC):
    """Abstract interface for password hashing operations"""

    @abstractmethod
    def hash_password(self, *, plain_password: SecretStr) -> str:
        """Hash a plain text password using SecretStr for security"""
        pass

    @abstractmethod
    def verify_password(self, *, plain_password: SecretStr, hashed_password: str) -> bool:
        """Verify a plain text password against a hashed password using SecretStr"""
        pass
