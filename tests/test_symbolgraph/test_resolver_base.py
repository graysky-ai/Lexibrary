"""Tests for ``lexibrary.symbolgraph.resolver_base``.

Exercises :class:`~lexibrary.symbolgraph.resolver_base.FallbackResolver`
— the intra-file fuzzy-name-match resolver used for TypeScript and
JavaScript in Phase 2. The protocol itself is a structural type and is
exercised implicitly by the :class:`FallbackResolver` methods below.
"""

from __future__ import annotations

import sqlite3

import pytest

from lexibrary.ast_parser.models import CallSite
from lexibrary.symbolgraph.resolver_base import FallbackResolver
from lexibrary.symbolgraph.schema import ensure_schema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    """A fresh in-memory SQLite connection with the full symbol-graph schema."""
    connection = sqlite3.connect(":memory:")
    ensure_schema(connection)
    return connection


def _insert_file(conn: sqlite3.Connection, path: str) -> int:
    """Insert a ``files`` row and return its primary key."""
    cursor = conn.execute(
        "INSERT INTO files (path, language) VALUES (?, ?)",
        (path, "typescript"),
    )
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


def _insert_symbol(
    conn: sqlite3.Connection,
    file_id: int,
    *,
    name: str,
    symbol_type: str = "function",
    parent_class: str | None = None,
) -> int:
    """Insert a ``symbols`` row and return its primary key."""
    cursor = conn.execute(
        "INSERT INTO symbols (file_id, name, symbol_type, parent_class) VALUES (?, ?, ?, ?)",
        (file_id, name, symbol_type, parent_class),
    )
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


def _make_call(callee_name: str, *, caller_name: str = "caller") -> CallSite:
    """Build a :class:`CallSite` with sensible defaults for resolver tests."""
    return CallSite(
        caller_name=caller_name,
        callee_name=callee_name,
        receiver=None,
        line=1,
        is_method_call=False,
    )


# ---------------------------------------------------------------------------
# 1. Single intra-file match resolves
# ---------------------------------------------------------------------------


def test_fallback_resolver_single_intra_file_match_resolves(
    conn: sqlite3.Connection,
) -> None:
    """Exactly one ``function`` match in the caller's file resolves to that row."""
    file_id = _insert_file(conn, "src/example.ts")
    target_id = _insert_symbol(conn, file_id, name="helper")

    resolver = FallbackResolver(conn)
    call = _make_call("helper")

    assert resolver.resolve(call, file_id, "src/example.ts") == target_id


# ---------------------------------------------------------------------------
# 2. Ambiguity returns None
# ---------------------------------------------------------------------------


def test_fallback_resolver_ambiguous_returns_none(
    conn: sqlite3.Connection,
) -> None:
    """Two same-named candidates in the file → return ``None`` (never guess).

    The UNIQUE constraint on ``symbols`` is
    ``(file_id, name, symbol_type, parent_class)`` so two ``method`` rows
    with the same name can legally co-exist as long as they belong to
    different ``parent_class`` values. This mirrors the cross-class
    same-method-name collision the Sub-phase 2.0 schema correction
    enables.
    """
    file_id = _insert_file(conn, "src/example.ts")
    _insert_symbol(
        conn,
        file_id,
        name="render",
        symbol_type="method",
        parent_class="Alpha",
    )
    _insert_symbol(
        conn,
        file_id,
        name="render",
        symbol_type="method",
        parent_class="Beta",
    )

    resolver = FallbackResolver(conn)
    call = _make_call("render")

    assert resolver.resolve(call, file_id, "src/example.ts") is None


# ---------------------------------------------------------------------------
# 3. No match returns None
# ---------------------------------------------------------------------------


def test_fallback_resolver_no_match_returns_none(
    conn: sqlite3.Connection,
) -> None:
    """Zero candidates in the file → return ``None``.

    Also pins the "same-file only" contract: a matching symbol in
    *another* file must not resolve. ``FallbackResolver`` never reaches
    across files; cross-file TS/JS calls stay unresolved until Phase 6.
    """
    caller_file_id = _insert_file(conn, "src/caller.ts")
    other_file_id = _insert_file(conn, "src/other.ts")
    # Same name as the call below, but in a different file → must not resolve.
    _insert_symbol(conn, other_file_id, name="helper")

    resolver = FallbackResolver(conn)
    call = _make_call("helper")

    assert resolver.resolve(call, caller_file_id, "src/caller.ts") is None


# ---------------------------------------------------------------------------
# 4. Bare name extracted from a dotted ``callee_name``
# ---------------------------------------------------------------------------


def test_fallback_resolver_bare_name_extracted_from_dotted(
    conn: sqlite3.Connection,
) -> None:
    """``foo.bar.baz`` matches a ``baz`` symbol in the file.

    The fallback resolver strips every dotted prefix and looks up the
    trailing component, so calls like ``obj.method()`` or
    ``namespace.sub.helper()`` hit an intra-file symbol named ``method``
    or ``helper``. This is intentionally fuzzy — any false positive on a
    cross-file dotted call would require the file to also define a
    same-named symbol locally, at which point ambiguity returns ``None``.
    """
    file_id = _insert_file(conn, "src/example.ts")
    target_id = _insert_symbol(conn, file_id, name="baz")

    resolver = FallbackResolver(conn)
    call = _make_call("foo.bar.baz")

    assert resolver.resolve(call, file_id, "src/example.ts") == target_id
