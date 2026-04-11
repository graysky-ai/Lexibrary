"""User data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    """A user in the system."""

    id: str
    username: str
    email: str

    def display_name(self) -> str:
        """Return a display-friendly name."""
        return self.username

    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.username == "admin"

    def to_dict(self) -> dict[str, str]:
        """Serialize user to dictionary."""
        return {"id": self.id, "username": self.username, "email": self.email}


def create_user(username: str, email: str) -> User:
    """Factory function for creating users."""
    import uuid

    return User(id=str(uuid.uuid4()), username=username, email=email)


def validate_email(email: str) -> bool:
    """Validate email format."""
    return "@" in email and "." in email.split("@")[1]
