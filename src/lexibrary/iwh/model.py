"""Pydantic 2 model for IWH (I Was Here) inter-agent signal files."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IWHScope = Literal["warning", "incomplete", "blocked"]


class IWHFile(BaseModel):
    """Represents a parsed ``.iwh`` signal file.

    IWH files are ephemeral, directory-scoped signals left by one agent
    session to inform the next. They carry a scope (severity), free-form
    markdown body, and metadata about who created them and when.
    """

    author: str = Field(..., min_length=1)
    created: datetime
    scope: IWHScope
    body: str = ""
