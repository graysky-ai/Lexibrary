"""CLI package for Lexibrary — two entry points: lexi (agent) and lexictl (maintenance)."""

from __future__ import annotations

import os

# Silence BAML's default DEBUG-level prompt+response dump in CLI invocations.
# Agents running `lexi design update` etc. only need the confirmation line;
# the full BAML trace blows out context windows. Developers can still override
# via `BAML_LOG=DEBUG lexi ...` for targeted debugging.
os.environ.setdefault("BAML_LOG", "WARN")

from lexibrary.cli.lexi_app import lexi_app  # noqa: E402
from lexibrary.cli.lexictl_app import lexictl_app  # noqa: E402

__all__ = ["lexi_app", "lexictl_app"]
