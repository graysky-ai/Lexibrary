"""Symbol resolver protocol and fallback implementation.

Every language-specific resolver implements the :class:`SymbolResolver`
protocol — a single :meth:`resolve` method that maps a textual call-site
name to a concrete ``symbols.id`` (or ``None`` when no definite match
exists). See ``CN-023 Symbol Resolution`` for the design rationale.

This module ships the Phase 2 **base** layer:

- The :class:`SymbolResolver` :class:`~typing.Protocol` definition that
  :class:`lexibrary.symbolgraph.resolver_python.PythonResolver` and future
  TS/JS/Rust resolvers implement.
- :class:`FallbackResolver`, an intra-file fuzzy name match used for any
  language without a dedicated resolver. Phase 2 wires this into the
  builder for TypeScript and JavaScript — a name only resolves when there
  is exactly one matching symbol in the caller's own file. Any cross-file
  TS/JS call lands in ``unresolved_calls`` until Phase 6 ships a real
  TS/JS resolver with ``tsconfig.json`` path support. Returning ``None``
  on ambiguity is intentional so we never point at the wrong target.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from lexibrary.ast_parser.models import CallSite


class SymbolResolver(Protocol):
    """Protocol implemented by every language-specific call-site resolver.

    A resolver converts a :class:`~lexibrary.ast_parser.models.CallSite`
    into a concrete ``symbols.id`` row by running whatever lookup strategy
    the language demands (e.g. import-aware lookups for Python,
    ``tsconfig.json`` path mapping for TS/JS in a later phase). Returning
    ``None`` signals that no definite target exists and the builder should
    record the call in ``unresolved_calls`` instead of ``calls``.
    """

    def resolve(
        self,
        call: CallSite,
        caller_file_id: int,
        caller_file_path: str,
    ) -> int | None:
        """Return the ``symbols.id`` of the callee, or ``None`` if unresolved."""
        ...


class FallbackResolver:
    """Intra-file fuzzy name match for languages without a dedicated resolver.

    Used for TypeScript and JavaScript in Phase 2. Deliberately scoped to
    the caller's own file: a name is only resolved if there is exactly
    one matching symbol in the same file as the call site. Any cross-file
    TS/JS call lands in ``unresolved_calls`` until Phase 6 ships a real
    TS/JS resolver with ``tsconfig.json`` path support. Returns ``None`` on
    ambiguity so we never point at the wrong target.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def resolve(
        self,
        call: CallSite,
        caller_file_id: int,
        caller_file_path: str,
    ) -> int | None:
        """Return the callee ``symbols.id`` when exactly one intra-file match exists.

        The bare name is extracted from ``call.callee_name`` by taking the
        final dotted component — e.g. ``foo.bar.baz`` becomes ``baz``. The
        lookup is then restricted to the caller's own file and to symbol
        types that can actually be invoked (``function``, ``method``,
        ``class``). Returns ``None`` on ambiguity (>1 row) or on no match
        (0 rows) so the builder correctly records an unresolved call.
        """
        bare = call.callee_name.rsplit(".", 1)[-1]
        rows = self._conn.execute(
            "SELECT id FROM symbols "
            "WHERE name = ? "
            "  AND file_id = ? "
            "  AND symbol_type IN ('function', 'method', 'class')",
            (bare, caller_file_id),
        ).fetchall()
        return rows[0][0] if len(rows) == 1 else None
