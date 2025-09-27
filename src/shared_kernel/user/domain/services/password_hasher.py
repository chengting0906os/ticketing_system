from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    """Abstract interface for password hashing operations"""

    @abstractmethod
    def hash_password(self, plain_password: str) -> str:
        """Hash a plain text password"""
        pass

    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain text password against a hashed password"""
        pass
