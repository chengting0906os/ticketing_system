"""Shared state and utilities for user steps."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.user.domain.user_model import Base, User
import hashlib
from typing import Optional, Dict, Any


class UserState:
    """Class to hold shared state between user steps."""
    session: Optional[Session] = None
    engine: Any = None
    user_data: Dict[str, str] = {}
    created_user: Optional[User] = None
    
    @classmethod
    def reset(cls):
        """Reset state and clean up database."""
        if cls.session:
            cls.session.rollback()
            cls.session.close()
        cls.user_data = {}
        cls.created_user = None
    
    @classmethod
    def setup_db(cls):
        """Set up test database connection."""
        # Use SQLite for testing (synchronous)
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        SessionLocal = sessionmaker(bind=cls.engine)
        cls.session = SessionLocal()  # This is guaranteed to be not None after setup
    
    @classmethod
    def hash_password(cls, password: str) -> str:
        """Simple password hashing for testing."""
        return hashlib.sha256(password.encode()).hexdigest()
