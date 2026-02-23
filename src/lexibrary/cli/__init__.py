"""CLI package for Lexibrary — two entry points: lexi (agent) and lexictl (maintenance)."""

from __future__ import annotations

from lexibrary.cli.lexi_app import lexi_app
from lexibrary.cli.lexictl_app import lexictl_app

__all__ = ["lexi_app", "lexictl_app"]
