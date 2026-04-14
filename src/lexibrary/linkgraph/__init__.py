"""SQLite link graph index for cross-artifact queries.

The link graph is a derived, rebuildable SQLite index that accelerates:
- Reverse dependency lookups ("what imports this file?")
- Tag search across all artifact types
- Full-text search via FTS5
- Concept alias resolution
- Convention inheritance
- Multi-hop graph traversal

Storage: ``.lexibrary/index.db`` (gitignored, rebuilt by ``lexictl update``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lexibrary.linkgraph.health import (
    IndexHealth,
    read_index_health,
)
from lexibrary.linkgraph.query import (
    ArtifactResult,
    BuildSummaryEntry,
    ConventionResult,
    LinkGraph,
    LinkGraphUnavailable,
    LinkResult,
    TraversalNode,
    extract_dependents,
    open_index,
)
from lexibrary.linkgraph.schema import (
    SCHEMA_VERSION,
    check_schema_version,
    ensure_schema,
)

if TYPE_CHECKING:
    from lexibrary.linkgraph.builder import (
        BuildResult,
        IndexBuilder,
        build_index,
    )

__all__ = [
    "ArtifactResult",
    "BuildResult",
    "BuildSummaryEntry",
    "ConventionResult",
    "IndexBuilder",
    "IndexHealth",
    "LinkGraph",
    "LinkGraphUnavailable",
    "LinkResult",
    "SCHEMA_VERSION",
    "TraversalNode",
    "build_index",
    "check_schema_version",
    "ensure_schema",
    "extract_dependents",
    "open_index",
    "read_index_health",
]


def __getattr__(name: str) -> object:
    """Lazy import for builder symbols to avoid circular import.

    The builder module depends on ``archivist.dependency_extractor`` which
    in turn imports ``archivist.pipeline`` which imports back into
    ``linkgraph.builder``.  Deferring the builder import until actual
    attribute access breaks the cycle at module-load time.
    """
    if name in ("BuildResult", "IndexBuilder", "build_index"):
        from lexibrary.linkgraph import builder as _builder

        return getattr(_builder, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
