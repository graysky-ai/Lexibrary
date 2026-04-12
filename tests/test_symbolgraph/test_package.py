"""Smoke tests for the ``lexibrary.symbolgraph`` package public API.

Pins the re-export surface so downstream code can rely on stable imports
from :mod:`lexibrary.symbolgraph`. If the package ``__init__`` drifts from
the documented API (names added to or removed from ``__all__`` without
updating the imports), these tests fail.
"""

from __future__ import annotations


def test_star_import_exposes_all_names() -> None:
    """``from lexibrary.symbolgraph import *`` must yield every ``__all__`` entry."""
    namespace: dict[str, object] = {}
    exec("from lexibrary.symbolgraph import *", namespace)  # noqa: S102
    # Re-read the canonical __all__ from the package itself to avoid drift.
    from lexibrary import symbolgraph

    for name in symbolgraph.__all__:
        assert name in namespace, f"{name!r} missing from star import namespace"


def test_schema_version_is_three() -> None:
    """``SCHEMA_VERSION`` is re-exported and equals ``3`` after Phase 7."""
    from lexibrary.symbolgraph import SCHEMA_VERSION

    assert SCHEMA_VERSION == 3
