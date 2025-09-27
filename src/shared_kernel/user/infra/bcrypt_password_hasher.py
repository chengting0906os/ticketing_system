import bcrypt

from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.domain.services.password_hasher import PasswordHasher


class BcryptPasswordHasher(PasswordHasher):
    """Concrete bcrypt implementation of PasswordHasher"""

    @Logger.io
    def hash_password(self, plain_password: str) -> str:
        password_bytes = plain_password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')

    @Logger.io
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
