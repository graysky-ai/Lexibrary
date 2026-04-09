"""Authentication login module."""
from __future__ import annotations


def authenticate(username: str, password: str) -> bool:
    """Authenticate a user with username and password."""
    return username == "admin" and password == "secret"


def logout(session_id: str) -> None:
    """End a user session."""
    pass
