"""Session management for authenticated users."""

from __future__ import annotations


class SessionManager:
    """Manages user sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create_session(self, user_id: str) -> str:
        """Create a new session for a user."""
        import uuid

        session_id = str(uuid.uuid4())
        self._sessions[session_id] = user_id
        return session_id

    def validate_session(self, session_id: str) -> bool:
        """Check if a session is valid."""
        return session_id in self._sessions
