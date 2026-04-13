"""Impact analysis service -- dependency tree for a source file.

Extracts the business logic from the ``lexi impact`` CLI handler into a
pure-data service.  Returns :class:`ImpactResult` with no terminal output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.artifacts.design_file_parser import parse_design_file_frontmatter
from lexibrary.config.schema import LexibraryConfig
from lexibrary.linkgraph import open_index
from lexibrary.utils.paths import mirror_path

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DependentNode:
    """A single node in the reverse-dependency tree.

    Attributes
    ----------
    path:
        Project-relative path of the dependent file.
    depth:
        How many hops from the target file (1 = direct dependent).
    description:
        One-line description from the design file, or ``None``.
    open_stack_posts:
        List of ``"<path> (<title>)"`` strings for open stack posts
        that reference this dependent.
    """

    path: str
    depth: int
    description: str | None = None
    open_stack_posts: list[str] = field(default_factory=list)


@dataclass
class ImpactResult:
    """Result of an impact analysis.

    Attributes
    ----------
    target_path:
        Project-relative path of the file that was analysed.
    dependents:
        Ordered list of :class:`DependentNode` objects representing
        reverse dependents discovered by the link-graph traversal.
    """

    target_path: str
    dependents: list[DependentNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------


def analyse_impact(
    target: Path,
    project_root: Path,
    config: LexibraryConfig,
    *,
    depth: int = 1,
) -> ImpactResult:
    """Analyse reverse dependents of *target* in the link graph.

    Parameters
    ----------
    target:
        Absolute path to the source file to analyse.
    project_root:
        Absolute path to the project root.
    config:
        Loaded project configuration.
    depth:
        Maximum traversal depth (clamped to 1--3).

    Returns
    -------
    ImpactResult
        The analysis result.  ``dependents`` is empty when the file has
        no inbound ``ast_import`` edges or when no link graph exists.

    Raises
    ------
    FileOutsideScopeError
        When *target* is outside all configured ``scope_roots``.
    LinkGraphMissingError
        When no link graph index database is found.
    """
    rel_path = str(target.relative_to(project_root))
    effective_depth = max(1, min(depth, 3))

    link_graph = open_index(project_root)
    if link_graph is None:
        raise LinkGraphMissingError

    try:
        nodes = link_graph.traverse(
            rel_path,
            max_depth=effective_depth,
            link_types=["ast_import"],
            direction="inbound",
        )
    finally:
        link_graph.close()

    if not nodes:
        return ImpactResult(target_path=rel_path)

    # Build DependentNode list with design descriptions & stack posts
    link_graph_for_stack = open_index(project_root)

    dependents: list[DependentNode] = []
    for node in nodes:
        # Design-file description
        description: str | None = None
        design_path = mirror_path(project_root, project_root / node.path)
        fm = parse_design_file_frontmatter(design_path)
        if fm is not None and fm.description:
            description = fm.description

        # Open stack posts referencing this dependent
        open_posts: list[str] = []
        if link_graph_for_stack is not None:
            stack_links = link_graph_for_stack.reverse_deps(node.path, link_type="stack_file_ref")
            for slink in stack_links:
                stack_artifact = link_graph_for_stack.get_artifact(slink.source_path)
                if stack_artifact is not None and stack_artifact.status == "open":
                    open_posts.append(
                        f"{stack_artifact.path} ({stack_artifact.title or 'untitled'})"
                    )

        dependents.append(
            DependentNode(
                path=node.path,
                depth=node.depth,
                description=description,
                open_stack_posts=open_posts,
            )
        )

    if link_graph_for_stack is not None:
        link_graph_for_stack.close()

    return ImpactResult(target_path=rel_path, dependents=dependents)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FileOutsideScopeError(Exception):
    """Raised when the target file is outside all configured scope_roots.

    Callers constructing the exception message should follow Block A:
    ``f"{source_path} is outside all configured scope_roots: "
    f"{[r.path for r in config.scope_roots]}"``.
    """


class LinkGraphMissingError(Exception):
    """Raised when no link graph index database exists."""
