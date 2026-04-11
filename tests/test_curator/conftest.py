"""Pytest fixtures for curator test suite.

Provides paths to the pre-built curator test fixture directories used by
curator phase tests (validation, consistency, comment integration, etc.).

The ``curator_library_path`` fixture points to the static fixture at
``tests/fixtures/curator_library/`` which contains planted issues for all
curator phases.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "curator_library"


@pytest.fixture()
def curator_library_path(tmp_path: Path) -> Path:
    """Return path to an isolated copy of the curator test library fixture.

    Creates a fresh copy in ``tmp_path`` so tests can modify files without
    affecting the static fixture on disk. The copy includes all planted
    issues (staleness, consistency, IWH, comments) and the pre-built
    SQLite link graph.
    """
    dest = tmp_path / "curator_library"
    shutil.copytree(_FIXTURE_DIR, dest)
    return dest
