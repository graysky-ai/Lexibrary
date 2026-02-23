"""Sample Python source for dependency extraction tests.

Contains absolute project imports, a third-party import, and a stdlib import.
"""

from __future__ import annotations

import os

import requests

from lexibrary.ast_parser.registry import get_parser
from lexibrary.config.schema import LexibraryConfig


def sample_function(config: LexibraryConfig) -> None:
    """Placeholder that references imports to keep linters happy."""
    _ = config
    _ = get_parser
    _ = requests
    _ = os
