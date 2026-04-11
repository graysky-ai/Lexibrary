"""Symbol graph — SQLite index of symbol-level code relationships.

Companion to the link graph (file-level edges). See CN-021 Symbol Graph and
docs/symbol-graph.md.
"""

from __future__ import annotations

from lexibrary.symbolgraph.builder import SymbolBuildResult, build_symbol_graph
from lexibrary.symbolgraph.health import SymbolGraphHealth, read_symbol_graph_health
from lexibrary.symbolgraph.query import (
    CallRow,
    ClassEdgeRow,
    SymbolGraph,
    SymbolMemberRow,
    SymbolRow,
    UnresolvedCallRow,
    UnresolvedClassEdgeRow,
    open_symbol_graph,
)
from lexibrary.symbolgraph.schema import SCHEMA_VERSION, ensure_schema

__all__ = [
    "CallRow",
    "ClassEdgeRow",
    "SCHEMA_VERSION",
    "SymbolBuildResult",
    "SymbolGraph",
    "SymbolGraphHealth",
    "SymbolMemberRow",
    "SymbolRow",
    "UnresolvedCallRow",
    "UnresolvedClassEdgeRow",
    "build_symbol_graph",
    "ensure_schema",
    "open_symbol_graph",
    "read_symbol_graph_health",
]
