"""Git hook installation and management for Lexibrary."""

from __future__ import annotations

from lexibrary.hooks.post_commit import install_post_commit_hook
from lexibrary.hooks.pre_commit import install_pre_commit_hook

__all__ = [
    "install_post_commit_hook",
    "install_pre_commit_hook",
]
